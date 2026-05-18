"""Polygon.io API wrapper — authentication, ticker cache, minute bars."""
import datetime
import os
import time
from concurrent.futures import ThreadPoolExecutor

from polygon import RESTClient

from . import config

_client: RESTClient | None = None


def get_client() -> RESTClient:
    global _client
    if _client is None:
        key = config.POLYGON_API_KEY
        if not key:
            raise RuntimeError(
                "POLYGON_API_KEY not set.\n"
                "Create a .env file with: POLYGON_API_KEY=your_key_here"
            )
        _client = RESTClient(api_key=key)
    return _client


def prev_trading_day(d: datetime.date) -> datetime.date:
    d -= datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


def load_tickers() -> list[str]:
    cache_file = config.TICKER_CACHE_FILE
    if os.path.exists(cache_file):
        age = datetime.datetime.now().timestamp() - os.path.getmtime(cache_file)
        if age < config.TICKER_CACHE_SECONDS:
            with open(cache_file) as f:
                tickers = [line.strip() for line in f if line.strip()]
            hours_left = int((config.TICKER_CACHE_SECONDS - age) / 3600)
            print(f"  Кэш: {len(tickers)} тикеров (обновится через {hours_left}ч)")
            return tickers

    print("  Загружаю тикеры с API (маркеткап <= $300M)...")
    client = get_client()
    tickers: list[str] = []
    skipped = 0
    page = 0
    try:
        for t in client.list_tickers(market="stocks", type="CS", active=True, limit=1000):
            mc = getattr(t, "market_cap", None)
            if mc is None or mc <= config.MAX_MARKET_CAP:
                tickers.append(t.ticker)
            else:
                skipped += 1
            page += 1
            if page % 1000 == 0:
                print(f"  ...{page} обработано, найдено {len(tickers)}", end="\r")
    except Exception as e:
        print(f"  Ошибка API: {e}")

    print(f"  Найдено: {len(tickers):,}  отсеяно (>$300M): {skipped:,}  всего: {page:,}")
    with open(cache_file, "w") as f:
        f.write("\n".join(tickers))
    print(f"  Кэш сохранён: {cache_file}")
    return tickers


def get_bars(ticker: str, date_str: str) -> list:
    try:
        return list(
            get_client().list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=date_str,
                to=date_str,
                adjusted=False,
                sort="asc",
                limit=1000,
            )
        )
    except Exception:
        return []


_EARNINGS_KW = {
    "earnings", "eps", "revenue", "quarterly", "fiscal quarter",
    "net income", "net loss", "guidance",
    "q1 ", "q2 ", "q3 ", "q4 ",
    "q1", "q2", "q3", "q4",
    "results", "financial results", "profit", "loss",
    "beat", "beats", "miss", "misses", "exceeded", "surpassed",
    "reports third", "reports second", "reports first", "reports fourth",
    "fourth quarter", "third quarter", "second quarter", "first quarter",
    "annual results", "full year", "fiscal year",
}


def has_earnings_news(ticker: str, pm_date: str) -> bool:
    """Return True if earnings-related news was published around pm_date."""
    try:
        d    = datetime.date.fromisoformat(pm_date)
        from_ = (d - datetime.timedelta(days=1)).isoformat() + "T00:00:00Z"
        to_   = (d + datetime.timedelta(days=1)).isoformat() + "T23:59:59Z"
        for news in get_client().list_ticker_news(
            ticker,
            published_utc_gte=from_,
            published_utc_lte=to_,
            limit=15,
        ):
            text = (
                (getattr(news, "title",       "") or "") + " " +
                (getattr(news, "description", "") or "")
            ).lower()
            if any(kw in text for kw in _EARNINGS_KW):
                return True
    except Exception:
        pass
    return False


def get_float_shares(tickers: list[str]) -> dict[str, float | None]:
    """Fetch weighted_shares_outstanding for a list of tickers in parallel."""
    client = get_client()

    def fetch_one(ticker: str) -> tuple[str, float | None]:
        try:
            d = client.get_ticker_details(ticker)
            val = getattr(d, "weighted_shares_outstanding", None) or \
                  getattr(d, "share_class_shares_outstanding", None)
            return ticker, float(val) if val else None
        except Exception:
            return ticker, None

    results: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        for ticker, val in pool.map(fetch_one, tickers):
            results[ticker] = val
    return results


def get_snapshots(tickers: list[str]) -> dict:
    client = get_client()
    snapshots: dict = {}
    for i in range(0, len(tickers), config.SNAPSHOT_CHUNK):
        chunk = tickers[i : i + config.SNAPSHOT_CHUNK]
        try:
            for s in client.get_snapshot_all("stocks", tickers=chunk):
                snapshots[s.ticker] = s
        except Exception:
            pass
        done = min(i + config.SNAPSHOT_CHUNK, len(tickers))
        print(f"  {done}/{len(tickers)}", end="\r")
        time.sleep(0.1)
    return snapshots
