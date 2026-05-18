"""Runtime configuration — all thresholds and limits in one place."""
import os
from dotenv import load_dotenv

load_dotenv()

POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")

# ── Trading thresholds ────────────────────────────────────────
MIN_POST_MOVE_PCT_A: float = 40.0   # Block A: min after-hours move
MIN_POST_MOVE_PCT_C: float = 30.0   # Block C: min after-hours move
MIN_PRE_MOVE_PCT_B: float  = 30.0   # Block B: min pre-market move

MIN_PRICE:          float = 0.50
MAX_PRICE:          float = 100.0
MAX_MARKET_CAP:     int   = 300_000_000   # $300M

MIN_VOLUME:         int   = 100_000       # snapshot pre-filter
MAX_INTRA_BREAKOUT: float = 0.10          # intraday may exceed high by max 10%
MIN_PREMKT_FLOW:    int   = 2_000_000     # pre-market money flow ($2M)

# ── Misc ─────────────────────────────────────────────────────
EXTRA_TICKERS:        list[str] = []   # manually added tickers
TICKER_CACHE_SECONDS: int       = 86_400
TICKER_CACHE_FILE:    str       = "ticker_cache.txt"
FETCH_WORKERS:        int       = 10
SNAPSHOT_CHUNK:       int       = 250
