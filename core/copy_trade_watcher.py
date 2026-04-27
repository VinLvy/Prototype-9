"""
core/copy_trade_watcher.py
--------------------------
Polls the Polymarket Data API for new trades made by a target wallet address.
Emits trade events to an async queue for downstream copy-trade execution.

Actual Data API response schema (verified):
  proxyWallet, side (BUY/SELL), asset (token_id), conditionId, size, price,
  timestamp, title, slug, outcome ("Up"/"Down"), outcomeIndex, transactionHash, ...

Filter logic:
    - Only emit BUY trades (we copy entries, not exits/sells)
    - Only emit trades for 5m/15m Up-Down markets (BTC, ETH, SOL, XRP) via slug
    - De-duplicate by transactionHash (never re-emit seen trades)
    - On first poll, seed seen_ids WITHOUT emitting (avoids replaying history)
    - Poll every POLL_INTERVAL_S seconds
"""

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, Optional, Set

import aiohttp

DATA_API_BASE = "https://data-api.polymarket.com"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
POLL_INTERVAL_S = 1.5  # 1-2s balance between speed and rate limit

# Markets to mirror: 5m (and 15m fallback) up-down crypto slugs
ALLOWED_MARKET_PATTERN = re.compile(
    r"(btc|eth|sol|xrp|bnb)-updown-(5m|15m)",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class CopyTradeWatcher:
    """
    Continuously polls Polymarket Data API for new BUY trades by a target wallet.
    Yields normalized signal dicts compatible with ExecutionEngine.
    """

    def __init__(self, target_wallet: str):
        self.target_wallet = target_wallet.lower()
        self._seen_tx: Set[str] = set()
        self._initialized = False  # True after first poll seeds seen_ids
        # Cache conditionId -> {yes_token_id, no_token_id, end_date_iso}
        self._token_cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # API Fetch
    # ------------------------------------------------------------------

    async def _fetch_recent_trades(self, session: aiohttp.ClientSession) -> list:
        """Fetch the latest trades by target wallet from Data API."""
        url = f"{DATA_API_BASE}/trades"
        params = {
            "user": self.target_wallet,
            "limit": 20,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"Data API returned {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("Data API fetch timed out.")
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
        return []

    async def _resolve_token_ids(
        self, session: aiohttp.ClientSession, condition_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve YES/NO token IDs and endDate for a conditionId via Gamma API.
        Results are cached per conditionId.
        """
        if condition_id in self._token_cache:
            return self._token_cache[condition_id]

        url = f"{GAMMA_API_BASE}/markets"
        try:
            async with session.get(
                url,
                params={"condition_id": condition_id},
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                market = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
                if not market:
                    return None

                raw = market.get("clobTokenIds", "[]")
                token_ids = json.loads(raw) if isinstance(raw, str) else raw
                if len(token_ids) < 2:
                    return None

                meta = {
                    "yes_token_id": token_ids[0],
                    "no_token_id":  token_ids[1],
                    "end_date_iso": market.get("endDate"),
                }
                self._token_cache[condition_id] = meta
                return meta
        except Exception as e:
            logger.error(f"Token ID lookup failed for {condition_id}: {e}")
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_allowed_market(self, slug: str) -> bool:
        return bool(ALLOWED_MARKET_PATTERN.search(slug or ""))

    def _parse_side(self, outcome: str, outcome_index: int) -> Optional[str]:
        """
        Map outcome string or outcomeIndex to YES/NO.
        Polymarket convention for Up/Down markets:
          outcome="Up" / outcomeIndex=0 → YES token
          outcome="Down" / outcomeIndex=1 → NO token
        """
        o = (outcome or "").strip().lower()
        if o in ("yes", "up") or outcome_index == 0:
            return "YES"
        if o in ("no", "down") or outcome_index == 1:
            return "NO"
        return None

    # ------------------------------------------------------------------
    # Main watcher loop
    # ------------------------------------------------------------------

    async def watch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator. Yields copy-trade signal dicts on new BUY trades.

        First poll: seeds _seen_tx with existing hashes (no emission) to avoid
        replaying old trade history on startup.
        """
        logger.info(
            f"CopyTradeWatcher: monitoring {self.target_wallet} "
            f"every {POLL_INTERVAL_S}s"
        )

        async with aiohttp.ClientSession() as session:
            while True:
                trades = await self._fetch_recent_trades(session)

                # --- First poll: seed seen set, don't emit ---
                if not self._initialized:
                    for t in trades:
                        tx = t.get("transactionHash", "")
                        if tx:
                            self._seen_tx.add(tx)
                    self._initialized = True
                    logger.info(
                        f"CopyTradeWatcher initialized. "
                        f"Seeded {len(self._seen_tx)} existing tx hashes. Watching for new trades..."
                    )
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue

                # --- Subsequent polls: emit only genuinely new trades ---
                for trade in trades:
                    tx = trade.get("transactionHash", "")
                    if not tx or tx in self._seen_tx:
                        continue
                    self._seen_tx.add(tx)

                    # Only copy BUY orders (not exits/sells)
                    if trade.get("side", "").upper() != "BUY":
                        logger.debug(f"[COPY] Skipped SELL trade {tx[:10]}...")
                        continue

                    slug        = trade.get("slug", "")
                    condition_id = trade.get("conditionId", "")
                    outcome     = trade.get("outcome", "")
                    outcome_idx = trade.get("outcomeIndex", -1)
                    price       = trade.get("price", 0.0)
                    title       = trade.get("title", slug)

                    # Market filter
                    if not self._is_allowed_market(slug):
                        logger.debug(f"[COPY] Skipped non-target market: {slug}")
                        continue

                    try:
                        price = float(price)
                    except (ValueError, TypeError):
                        continue
                    if price <= 0:
                        continue

                    # Resolve YES/NO token IDs
                    token_meta = await self._resolve_token_ids(session, condition_id)
                    if token_meta is None:
                        logger.warning(f"[COPY] Could not resolve token IDs for {condition_id}")
                        continue

                    side = self._parse_side(outcome, outcome_idx)
                    if side is None:
                        logger.warning(f"[COPY] Unknown outcome '{outcome}' (idx={outcome_idx}) on {slug}")
                        continue

                    signal = {
                        "market_id":              title,
                        "condition_id":           condition_id,
                        "yes_token_id":           token_meta["yes_token_id"],
                        "no_token_id":            token_meta["no_token_id"],
                        "side":                   side,
                        "execution_price":        price,
                        "end_date_iso":           token_meta.get("end_date_iso"),
                        "reason":                 "COPY_ENTRY",
                        "recommended_size_usd":   1.0,
                        "spread":                 0.0,
                        "estimated_profit_per_share": 0.0,
                        "source_trade_id":        tx,
                    }

                    logger.info(
                        f"[COPY] ✓ New BUY detected: {side} on {slug} "
                        f"@ {price:.3f} | tx={tx[:14]}..."
                    )
                    yield signal

                await asyncio.sleep(POLL_INTERVAL_S)
