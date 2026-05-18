"""Core screener logic — block A/B/C classification and full scan."""
import datetime
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

from . import config
from .client import get_bars, get_snapshots, load_tickers
from .sessions import SessionData, fmt, fmt_vol, initial_move_label, parse_sessions, pct

ET = ZoneInfo("America/New_York")


def _classify(
    s_pm: SessionData,
    s_nx: SessionData,
    *,
    intraday_started: bool,
    is_today: bool,
) -> tuple[str | None, dict]:
    """Return (block, record) or (None, {}) if ticker passes no block."""
    reg_close = s_pm["regular_close"]
    pm_high   = s_pm["pm_high"]
    pm_vol    = s_pm["pm_volume"]
    pre_high  = s_nx["pre_high"]
    pre_vol   = s_nx["pre_volume"]
    pre_flow  = s_nx["pre_moneyflow"]
    intra_h   = s_nx["intra_high"]
    intra_o   = s_nx["intra_open"]

    price_ref = intra_o or reg_close
    if not price_ref or not (config.MIN_PRICE <= price_ref <= config.MAX_PRICE):
        return None, {}
    if intra_o and reg_close and intra_o <= reg_close:
        return None, {}

    pm_move  = pct(pm_high,  reg_close)
    pre_move = pct(pre_high, reg_close)
    gap      = pct(intra_o,  reg_close)
    check_intra = intraday_started or not is_today

    base = dict(
        reg_close=reg_close, pm_high=pm_high, pm_move=pm_move, pm_vol=pm_vol,
        pre_high=pre_high, pre_move=pre_move, pre_vol=pre_vol, pre_flow=pre_flow,
        intra_h=intra_h, gap=gap,
        intra_vol_15=s_nx["intra_volume_15"],
    )

    # Block A — PM pump, high not broken in PRE or intraday
    if (
        pm_high and pm_vol
        and pm_move and pm_move >= config.MIN_POST_MOVE_PCT_A
        and gap is not None and gap > 0
        and (not pre_high or pre_high < pm_high)
        and (not check_intra or not intra_h or intra_h <= pm_high * (1 + config.MAX_INTRA_BREAKOUT))
        and pre_vol
        and pre_flow >= config.MIN_PREMKT_FLOW
    ):
        return "A", {**base, "sort_key": pm_move}

    # Block B — PRE pump, no prior PM move, high not broken in intraday
    if (
        pre_high and pre_vol
        and pre_move and pre_move >= config.MIN_PRE_MOVE_PCT_B
        and (not pm_move or pm_move < config.MIN_PRE_MOVE_PCT_B)
        and (not check_intra or not intra_h or intra_h <= pre_high * (1 + config.MAX_INTRA_BREAKOUT))
    ):
        return "B", {**base, "sort_key": pre_move}

    # Block C — PM pump + PRE continuation, high not broken in intraday
    if (
        pm_high and pm_vol
        and pm_move and pm_move >= config.MIN_POST_MOVE_PCT_C
        and pre_high and pre_vol
        and pre_high > pm_high
        and (not check_intra or not intra_h or intra_h <= pre_high * (1 + config.MAX_INTRA_BREAKOUT))
    ):
        return "C", {**base, "sort_key": pre_move or pm_move}

    return None, {}


def screen(
    pm_date: str,
    next_date: str,
    *,
    is_today: bool = False,
    on_progress: Callable[[str, float], None] | None = None,
) -> dict:
    """Core screening function. Returns structured data for CLI and web UI.

    Returns:
        {
            "blocks": {"A": [...], "B": [...], "C": [...]},
            "bars":   {ticker: (bars_pm, bars_nx)},   # only matched tickers
            "meta":   {...},
        }

    on_progress(stage, value) is called with:
        stage="snapshots" value=0..1
        stage="fetching"  value=0..1  (fraction of candidates done)
    """
    now_utc = datetime.datetime.now(tz=datetime.timezone.utc)
    now_et  = now_utc.astimezone(ET)
    intraday_started  = is_today and now_et.time() >= datetime.time(9, 30)
    premarket_started = is_today and now_et.time() >= datetime.time(4, 0)
    cutoff_utc        = now_utc if is_today else None

    all_tickers = load_tickers()
    for t in config.EXTRA_TICKERS:
        if t not in all_tickers:
            all_tickers.append(t)

    if on_progress:
        on_progress("snapshots", 0.0)
    snapshots = get_snapshots(all_tickers)
    if on_progress:
        on_progress("snapshots", 1.0)

    candidates = [
        ticker for ticker, snap in snapshots.items()
        if getattr(snap.day, "volume", None) and snap.day.volume >= config.MIN_VOLUME
    ]
    for t in config.EXTRA_TICKERS:
        if t not in candidates:
            candidates.append(t)

    def fetch(ticker: str):
        bars_pm = get_bars(ticker, pm_date)
        bars_nx = get_bars(ticker, next_date)
        s_pm = parse_sessions(bars_pm)
        s_nx = parse_sessions(bars_nx, cutoff_utc=cutoff_utc)
        return ticker, s_pm, s_nx, bars_pm, bars_nx

    ticker_data: dict[str, tuple[SessionData, SessionData]] = {}
    ticker_bars: dict[str, tuple[list, list]] = {}
    done = 0
    total = len(candidates)

    with ThreadPoolExecutor(max_workers=config.FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch, t): t for t in candidates}
        for future in as_completed(futures):
            done += 1
            if on_progress:
                on_progress("fetching", done / total)
            try:
                ticker, s_pm, s_nx, bars_pm, bars_nx = future.result()
                ticker_data[ticker] = (s_pm, s_nx)
                ticker_bars[ticker] = (bars_pm, bars_nx)
            except Exception:
                pass

    blocks: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    result_bars: dict[str, tuple[list, list]] = {}

    for ticker in candidates:
        if ticker not in ticker_data:
            continue
        s_pm, s_nx = ticker_data[ticker]
        block, record = _classify(
            s_pm, s_nx,
            intraday_started=intraday_started,
            is_today=is_today,
        )
        if block:
            record["ticker"] = ticker
            record["move_info"] = initial_move_label(
                record["pm_high"], record["pre_high"], record["reg_close"]
            )
            blocks[block].append(record)
            result_bars[ticker] = ticker_bars[ticker]

    for rows in blocks.values():
        rows.sort(key=lambda r: r["sort_key"] or 0, reverse=True)

    return {
        "blocks": blocks,
        "bars": result_bars,
        "meta": {
            "pm_date":            pm_date,
            "next_date":          next_date,
            "candidates":         total,
            "is_today":           is_today,
            "premarket_started":  premarket_started,
            "intraday_started":   intraday_started,
            "now_et":             now_et,
        },
    }


def run_screener(pm_date: str, next_date: str, *, is_today: bool = False) -> None:
    """CLI entry point — runs screen() and prints formatted results."""
    now_utc = datetime.datetime.now(tz=datetime.timezone.utc)
    now_et  = now_utc.astimezone(ET)
    intraday_started  = is_today and now_et.time() >= datetime.time(9, 30)
    premarket_started = is_today and now_et.time() >= datetime.time(4, 0)

    print(f"\n{'='*68}")
    print(f"  Screener  |  Постмаркет: {pm_date}  ->  {next_date}")
    if is_today:
        status_pre   = "OK" if premarket_started else "нет"
        status_intra = "OK" if intraday_started  else "нет"
        print(f"  ET: {now_et.strftime('%H:%M')}  Премаркет: {status_pre}  Интрадей: {status_intra}")
    print(f"{'='*68}")

    done_count = [0]

    def on_progress(stage: str, value: float) -> None:
        if stage == "snapshots" and value == 0:
            print("  Snapshots...")
        elif stage == "fetching":
            n = int(value * 100)
            print(f"  Загружаю бары... {n}%          ", end="\r")

    result = screen(pm_date, next_date, is_today=is_today, on_progress=on_progress)
    print(f"\n  Анализирую {result['meta']['candidates']} кандидатов...")
    _print_results(result["blocks"], pm_date, next_date)


def _print_results(
    blocks: dict[str, list[dict]],
    pm_date: str,
    next_date: str,
) -> None:
    sep = "  " + "-" * 72

    titles = {
        "A": f"БЛОК A — PM +{config.MIN_POST_MOVE_PCT_A}%, хай не переписан",
        "B": f"БЛОК B — PRE +{config.MIN_PRE_MOVE_PCT_B}%, без PM мува, хай не переписан",
        "C": f"БЛОК C — PM +{config.MIN_POST_MOVE_PCT_C}%, хай переписан в PRE, не в интрадей",
    }

    for block_id, rows in blocks.items():
        print(f"\n{'='*72}")
        print(f"  {titles[block_id]}  |  Найдено: {len(rows)}")
        print(f"{'='*72}")
        if not rows:
            print("  Нет тикеров.")
            continue
        for r in rows:
            move = r["move_info"] or f"InitialMov={fmt(r['sort_key'])}%"
            print(f"  {r['ticker']:<7}  {move}")
            print(f"           PM({pm_date}): {fmt_vol(r['pm_vol']):<8}  "
                  f"PRE: {fmt_vol(r['pre_vol']):<8}  "
                  f"INTRA до 15:00: {fmt_vol(r['intra_vol_15'])}")
        print(sep)
