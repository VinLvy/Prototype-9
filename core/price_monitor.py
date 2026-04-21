"""
core/price_monitor.py
----------------------
Connects to Polymarket's CLOB WebSocket to stream real-time price ticks.

Correct WSS endpoint (per docs):
    wss://ws-subscriptions-clob.polymarket.com/ws/market

Protocol:
    1. Connect to WSS endpoint
    2. Send subscription message: {"assets_ids": [...token_ids], "type": "market"}
    3. Receive event_type frames: "book", "price_change", "best_bid_ask", "last_trade_price"
    4. Send heartbeat ping {} every 10 seconds

CRITICAL: Polymarket does NOT use human-readable market slugs over WebSocket.
Markets are identified by numeric token IDs (asset_id). Two token IDs exist per binary
market: one for YES, one for NO. These are sourced from the Gamma REST API field
`clobTokenIds` (JSON-encoded array string).
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, Any, List, Optional

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

# ---------------------------------------------------------------------------
# Constants — per official Polymarket documentation
# ---------------------------------------------------------------------------
GAMMA_API_BASE   = "https://gamma-api.polymarket.com"
WSS_ENDPOINT     = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL_S  = 10   # docs: send heartbeat {} every 10s
RECONNECT_DELAY_S = 5   # backoff before reconnect attempt


logger = logging.getLogger(__name__)


class PriceMonitor:
    """
    Discovers active Polymarket binary markets, resolves their YES/NO token IDs,
    then streams real-time price ticks via the CLOB WebSocket.

    Emitted tick format (normalized for ArbitrageDetector):
    {
        'market_id':   str,   # human-readable question or slug
        'condition_id': str,  # on-chain condition ID (0x...)
        'yes_token_id': str,  # numeric string token ID for YES side
        'no_token_id':  str,  # numeric string token ID for NO side
        'yes_price':   float, # best ask for YES token (cost to buy YES)
        'no_price':    float, # best ask for NO token  (cost to buy NO)
        'timestamp':   int    # unix ms from WSS message
    }
    """

    def __init__(
        self,
        markets: List[str],
        max_markets: int = 20,
        keyword_filter: Optional[str] = None,
    ):
        """
        Args:
            markets: List of market slugs or question substrings to target.
                     Empty list = auto-discover top active markets.
            max_markets: Cap on how many markets to subscribe to simultaneously.
            keyword_filter: Optional keyword to filter market questions
                            (e.g. 'BTC', 'bitcoin').
        """
        self.target_slugs   = markets
        self.max_markets    = max_markets
        self.keyword_filter = keyword_filter
        self._is_connected  = False
        self._ws            = None

        # Populated during market discovery:
        # { asset_id: {"market_id": str, "condition_id": str,
        #               "yes_token_id": str, "no_token_id": str} }
        self._token_map: Dict[str, Dict[str, Any]] = {}

        # Live price state per asset_id: {"best_bid": float, "best_ask": float}
        self._price_state: Dict[str, Dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Market Discovery — Gamma REST API
    # ------------------------------------------------------------------

    async def _discover_markets(self) -> List[Dict[str, Any]]:
        """
        Fetch active, open markets from the Gamma REST API.
        Returns list of dicts with keys: slug, question, conditionId, clobTokenIds.

        Endpoint: GET https://gamma-api.polymarket.com/markets
        Query:    active=true, closed=false, limit=<max_markets>
        """
        import config.settings as settings
        
        params = {
            "active": "true",
        }
        
        if settings.STRATEGY == "bonereaper":
            params["limit"] = 500
            params["order"] = "createdAt"
            params["ascending"] = "false"
        else:
            params["closed"] = "false"
            params["limit"] = self.max_markets * 3  # over-fetch to allow filtering
        url = f"{GAMMA_API_BASE}/markets"

        logger.info(f"Discovering active markets from {url} ...")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"Gamma API error {resp.status}: {await resp.text()}"
                    )
                markets_raw: List[Dict] = await resp.json()

        # Filter: must have CLOB token IDs (binary markets only)
        markets = [
            m for m in markets_raw
            if m.get("clobTokenIds") and m.get("enableOrderBook")
        ]

        if settings.STRATEGY == "bonereaper":
            import re
            from datetime import datetime, timezone, timedelta
            
            now = datetime.now(timezone.utc)
            window_cutoff = now - timedelta(minutes=10)  # tolak market yang closed > 10 menit lalu
            
            def is_in_window(m):
                end_raw = m.get("endDate") or m.get("endDateIso") or ""
                if not end_raw:
                    return True
                try:
                    end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                    return end_dt >= window_cutoff
                except Exception:
                    return True

            FIVE_MIN_SLUG_PATTERNS = [
                r"btc-updown-5m",
                r"eth-updown-5m", 
                r"sol-updown-5m",
                r"\d{1,2}:\d{2}(am|pm)?-\d{1,2}:\d{2}(am|pm)?",  # time range pattern
            ]
            regex_combined = re.compile("|".join(FIVE_MIN_SLUG_PATTERNS), re.IGNORECASE)
            
            filtered_markets = []
            for m in markets:
                target_str = (m.get("slug", "") + " " + m.get("question", "")).lower()
                # Gate 1: Regex is sufficient as Polymarket's `startDate` is now 24h in advance, breaking duration checks.
                if regex_combined.search(target_str) and is_in_window(m):
                    filtered_markets.append(m)
            markets = filtered_markets

        # Optional keyword filter
        if self.keyword_filter:
            kw = self.keyword_filter.lower()
            markets = [
                m for m in markets
                if kw in (m.get("question") or "").lower()
                or kw in (m.get("slug") or "").lower()
            ]

        # Optional slug filter
        if self.target_slugs:
            slugs_lower = {s.lower() for s in self.target_slugs}
            markets = [
                m for m in markets
                if (m.get("slug") or "").lower() in slugs_lower
            ]

        markets = markets[: self.max_markets]
        logger.info(f"Resolved {len(markets)} target markets.")
        return markets

    def _build_token_map(self, markets: List[Dict]) -> List[str]:
        """
        Builds self._token_map and returns flat list of all token IDs to subscribe.

        clobTokenIds is a JSON-encoded string in the API response:
            "[\"<yes_token_id>\", \"<no_token_id>\"]"
        Index 0 = YES token, index 1 = NO token (per Polymarket convention).
        """
        all_token_ids = []

        for m in markets:
            try:
                token_ids: List[str] = json.loads(m["clobTokenIds"])
            except (json.JSONDecodeError, KeyError):
                logger.warning(f"Skipping market {m.get('slug')}: bad clobTokenIds")
                continue

            if len(token_ids) < 2:
                logger.warning(f"Skipping market {m.get('slug')}: expected 2 token IDs")
                continue

            yes_id, no_id = token_ids[0], token_ids[1]
            market_label  = m.get("question") or m.get("slug") or m.get("conditionId", "UNKNOWN")
            condition_id  = m.get("conditionId", "")

            meta = {
                "market_id":    market_label,
                "condition_id": condition_id,
                "yes_token_id": yes_id,
                "no_token_id":  no_id,
                "end_date_iso": m.get("endDate"),
            }

            # Map both token IDs back to the same market metadata
            self._token_map[yes_id] = meta
            self._token_map[no_id]  = meta

            # Init price state
            self._price_state[yes_id] = {"best_bid": 0.0, "best_ask": 0.0}
            self._price_state[no_id]  = {"best_bid": 0.0, "best_ask": 0.0}

            all_token_ids.extend([yes_id, no_id])

        logger.info(f"Token map built: {len(self._token_map) // 2} markets, {len(all_token_ids)} token IDs")
        return all_token_ids

    # ------------------------------------------------------------------
    # WebSocket — Price Streaming
    # ------------------------------------------------------------------

    async def _send_subscription(self, ws, token_ids: List[str]):
        """
        Send initial subscription request per WSS protocol spec.
        Message format: {"assets_ids": [...], "type": "market"}
        """
        payload = {"assets_ids": token_ids, "type": "market"}
        await ws.send(json.dumps(payload))
        logger.info(f"Subscribed to {len(token_ids)} token IDs.")

    async def _heartbeat_loop(self, ws):
        """Send {} ping every PING_INTERVAL_S seconds."""
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL_S)
                await ws.send("{}")
                logger.debug("Heartbeat sent.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")

    def _process_message(self, raw: str) -> Optional[Dict[str, Any]]:
        """
        Parse a WSS message and return a normalized tick if a complete YES+NO
        price pair is available for a market, otherwise None.

        Handles event types: book, price_change, best_bid_ask, last_trade_price
        """
        try:
            msg = json.loads(raw)
            if isinstance(msg, list):
                if not msg:
                    return None
                for payload in msg:
                    # Polymarket occasionally batches events in an array
                    tick = self._process_single_payload(payload)
                    if tick is not None:
                        # For simplicity, returning the first complete tick if batched
                        return tick
                return None
            return self._process_single_payload(msg)
        except json.JSONDecodeError:
            return None  # ping/pong are "{}" — ignore

    def _process_single_payload(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:

        event_type = msg.get("event_type")
        ts         = int(msg.get("timestamp", time.time() * 1000))

        # --- Orderbook snapshot: extract best bid/ask from top of book ---
        if event_type == "book":
            asset_id = msg.get("asset_id")
            if asset_id not in self._price_state:
                return None
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 0.0
            self._price_state[asset_id] = {"best_bid": best_bid, "best_ask": best_ask}

        # --- Best bid/ask delta update (most frequent, lowest latency) ---
        elif event_type == "best_bid_ask":
            asset_id = msg.get("asset_id")
            if asset_id not in self._price_state:
                return None
            self._price_state[asset_id] = {
                "best_bid": float(msg.get("best_bid", 0)),
                "best_ask": float(msg.get("best_ask", 0)),
            }

        # --- Price change: iterate price_changes array ---
        elif event_type == "price_change":
            for change in msg.get("price_changes", []):
                asset_id = change.get("asset_id")
                if asset_id in self._price_state:
                    self._price_state[asset_id] = {
                        "best_bid": float(change.get("best_bid", 0)),
                        "best_ask": float(change.get("best_ask", 0)),
                    }

        # --- Last trade price: update best_ask as proxy ---
        elif event_type == "last_trade_price":
            asset_id = msg.get("asset_id")
            if asset_id in self._price_state:
                price = float(msg.get("price", 0))
                self._price_state[asset_id]["best_ask"] = price

        # --- Market resolved / closed reset ---
        elif event_type in ("market_resolved", "market_closed", "closed", "resolved"):
            condition_id = msg.get("condition_id")
            asset_id = msg.get("asset_id")
            
            if condition_id:
                # Clear all assets associated with this condition
                for asset, meta in self._token_map.items():
                    if meta.get("condition_id") == condition_id and asset in self._price_state:
                        self._price_state[asset] = {"best_bid": 0.0, "best_ask": 0.0}
            
            if asset_id and asset_id in self._price_state:
                self._price_state[asset_id] = {"best_bid": 0.0, "best_ask": 0.0}

        else:
            return None  # new_market, tick_size_change — not relevant here

        # After any price update, try to emit a complete tick for that market
        return self._try_emit_tick(
            self._token_map.get(msg.get("asset_id", "")),
            ts
        )

    def _try_emit_tick(self, meta: Optional[Dict], ts: int) -> Optional[Dict[str, Any]]:
        """
        If both YES and NO prices are non-zero for a market, return a normalized tick dict.
        """
        if meta is None:
            return None

        yes_id = meta["yes_token_id"]
        no_id  = meta["no_token_id"]

        yes_state = self._price_state.get(yes_id, {})
        no_state  = self._price_state.get(no_id,  {})

        # Use best_ask as the cost to BUY that side (what matters for arb)
        yes_price = yes_state.get("best_ask", 0.0)
        no_price  = no_state.get("best_ask", 0.0)

        if yes_price <= 0.0 or no_price <= 0.0:
            return None  # Incomplete — wait for both sides

        return {
            "market_id":    meta["market_id"],
            "condition_id": meta["condition_id"],
            "yes_token_id": yes_id,
            "no_token_id":  no_id,
            "yes_price":    yes_price,
            "no_price":     no_price,
            "timestamp":    ts,
            "end_date_iso": meta.get("end_date_iso"),
        }

    # ------------------------------------------------------------------
    # Public Interface — Async Generator
    # ------------------------------------------------------------------

    async def stream_prices(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator. Yields normalized price ticks as they arrive.

        Flow:
            1. Discover markets via Gamma REST API
            2. Build token ID map
            3. Connect to WSS endpoint
            4. Subscribe to all token IDs
            5. Parse messages and yield complete YES+NO tick pairs
            6. Auto-reconnect on disconnect with exponential backoff
        """
        reconnect_attempts = 0

        while True:
            try:
                # Step 1 & 2: Market discovery (moved inside loop to retry)
                markets   = await self._discover_markets()
                token_ids = self._build_token_map(markets)

                if not token_ids:
                    logger.warning("No token IDs resolved (no matching markets open). Retrying in 15s...")
                    await asyncio.sleep(15)
                    continue

                logger.info(f"Connecting to {WSS_ENDPOINT} ...")
                async with websockets.connect(
                    WSS_ENDPOINT,
                    ping_interval=None,  # We handle our own heartbeat
                    ping_timeout=None,
                ) as ws:
                    self._ws          = ws
                    self._is_connected = True
                    reconnect_attempts = 0

                    await self._send_subscription(ws, token_ids)

                    # Start heartbeat as background task
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

                    try:
                        async for raw_msg in ws:
                            tick = self._process_message(raw_msg)
                            if tick is not None:
                                yield tick
                    finally:
                        heartbeat_task.cancel()
                        self._is_connected = False

            except (ConnectionClosed, WebSocketException) as e:
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in {RECONNECT_DELAY_S}s...")
            except aiohttp.ClientError as e:
                logger.error(f"HTTP error during market discovery: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in stream_prices: {e}", exc_info=True)

            self._is_connected = False
            reconnect_attempts += 1
            delay = min(RECONNECT_DELAY_S * reconnect_attempts, 60)
            logger.info(f"Reconnect attempt #{reconnect_attempts} in {delay}s...")
            await asyncio.sleep(delay)