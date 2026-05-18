"""CLI menu and single-ticker analysis."""
import datetime
from zoneinfo import ZoneInfo

from . import config
from .client import get_bars, prev_trading_day
from .screener import run_screener
from .sessions import fmt, fmt_vol, initial_move_label, parse_sessions, pct

ET = ZoneInfo("America/New_York")


def analyze_ticker(ticker: str, pm_date: str, next_date: str, *, is_today: bool = False) -> None:
    now_utc = datetime.datetime.now(tz=datetime.timezone.utc)
    now_et  = now_utc.astimezone(ET)
    intraday_started = is_today and now_et.time() >= datetime.time(9, 30)
    cutoff_utc       = now_utc if is_today else None

    print(f"\n  {'='*60}")
    print(f"  Проверка: {ticker}  |  PM: {pm_date}  ->  {next_date}")
    print(f"  {'='*60}")

    s_pm = parse_sessions(get_bars(ticker, pm_date))
    s_nx = parse_sessions(get_bars(ticker, next_date), cutoff_utc=cutoff_utc)

    reg_close = s_pm["regular_close"]
    pm_high   = s_pm["pm_high"]
    pm_vol    = s_pm["pm_volume"]
    pre_high  = s_nx["pre_high"]
    pre_vol   = s_nx["pre_volume"]
    pre_flow  = s_nx["pre_moneyflow"]
    intra_h   = s_nx["intra_high"]
    intra_o   = s_nx["intra_open"]

    print(f"\n  Данные:")
    print(f"    Regular close {pm_date}:  {fmt(reg_close)}")
    print(f"    PM high {pm_date}:        {fmt(pm_high)}  (объём: {fmt_vol(pm_vol)})")
    print(f"    PRE high {next_date}:     {fmt(pre_high)}  (объём: {fmt_vol(pre_vol)}, поток: {fmt_vol(pre_flow)})")
    print(f"    Интрадей high {next_date}: {fmt(intra_h)}")
    print(f"    Гэп при открытии:          {fmt(pct(intra_o, reg_close))}%")
    if pm_high and reg_close:
        print(f"    PM мув от close:           {fmt(pct(pm_high, reg_close))}%")
    if pre_high and reg_close:
        print(f"    PRE мув от close:          {fmt(pct(pre_high, reg_close))}%")

    check_intra = intraday_started or not is_today
    price_ref   = intra_o or reg_close
    pm_move     = pct(pm_high, reg_close)
    pre_move    = pct(pre_high, reg_close)
    gap         = pct(intra_o, reg_close)

    # ── Block A ──────────────────────────────────────────────
    print(f"\n  {'─'*60}")
    print(f"  БЛОК A (PM +{config.MIN_POST_MOVE_PCT_A}%, хай не переписан):")
    if not price_ref or not (config.MIN_PRICE <= price_ref <= config.MAX_PRICE):
        print(f"    ❌ Цена вне диапазона ${config.MIN_PRICE}–${config.MAX_PRICE}")
    elif intra_o and reg_close and intra_o <= reg_close:
        print(f"    ❌ Open ({fmt(intra_o)}) не выше close ({fmt(reg_close)})")
    elif not pm_high or not pm_vol:
        print(f"    ❌ Нет постмаркет объёма")
    elif not pm_move or pm_move < config.MIN_POST_MOVE_PCT_A:
        print(f"    ❌ PM мув {fmt(pm_move)}% < {config.MIN_POST_MOVE_PCT_A}%")
    elif gap is not None and gap <= 0:
        print(f"    ❌ Нет гэпа вверх: {fmt(gap)}%")
    elif pre_high and pre_high >= pm_high:
        print(f"    ❌ PRE переписал PM хай: {fmt(pre_high)} >= {fmt(pm_high)}")
    elif check_intra and intra_h and intra_h > pm_high * (1 + config.MAX_INTRA_BREAKOUT):
        limit = pm_high * (1 + config.MAX_INTRA_BREAKOUT)
        print(f"    ❌ INTRA пробил PM хай > 10%: {fmt(intra_h)} > {fmt(limit)}")
    elif not pre_vol:
        print(f"    ❌ Нет объёма в премаркете")
    elif pre_flow < config.MIN_PREMKT_FLOW:
        print(f"    ❌ PRE поток {fmt_vol(pre_flow)} < ${config.MIN_PREMKT_FLOW // 1_000_000}M")
    else:
        print(f"    ✅ ПРОХОДИТ!")

    # ── Block B ──────────────────────────────────────────────
    print(f"\n  БЛОК B (PRE +{config.MIN_PRE_MOVE_PCT_B}%, без PM мува):")
    if not price_ref or not (config.MIN_PRICE <= price_ref <= config.MAX_PRICE):
        print(f"    ❌ Цена вне диапазона")
    elif intra_o and reg_close and intra_o <= reg_close:
        print(f"    ❌ Open ({fmt(intra_o)}) не выше close ({fmt(reg_close)})")
    elif not pre_high or not pre_vol:
        print(f"    ❌ Нет премаркет объёма")
    elif not pre_move or pre_move < config.MIN_PRE_MOVE_PCT_B:
        print(f"    ❌ PRE мув {fmt(pre_move)}% < {config.MIN_PRE_MOVE_PCT_B}%")
    elif pm_move and pm_move >= config.MIN_PRE_MOVE_PCT_B:
        print(f"    ❌ Был PM мув {fmt(pm_move)}% (это Блок A или C)")
    elif check_intra and intra_h and intra_h > pre_high * (1 + config.MAX_INTRA_BREAKOUT):
        limit = pre_high * (1 + config.MAX_INTRA_BREAKOUT)
        print(f"    ❌ INTRA пробил PRE хай > 10%: {fmt(intra_h)} > {fmt(limit)}")
    else:
        print(f"    ✅ ПРОХОДИТ!")

    # ── Block C ──────────────────────────────────────────────
    print(f"\n  БЛОК C (PM +{config.MIN_POST_MOVE_PCT_C}%, хай переписан в PRE):")
    if not price_ref or not (config.MIN_PRICE <= price_ref <= config.MAX_PRICE):
        print(f"    ❌ Цена вне диапазона")
    elif intra_o and reg_close and intra_o <= reg_close:
        print(f"    ❌ Open ({fmt(intra_o)}) не выше close ({fmt(reg_close)})")
    elif not pm_high or not pm_vol:
        print(f"    ❌ Нет постмаркет объёма")
    elif not pm_move or pm_move < config.MIN_POST_MOVE_PCT_C:
        print(f"    ❌ PM мув {fmt(pm_move)}% < {config.MIN_POST_MOVE_PCT_C}%")
    elif not pre_high or not pre_vol:
        print(f"    ❌ Нет премаркет объёма")
    elif pre_high <= pm_high:
        print(f"    ❌ PRE не переписал PM хай: {fmt(pre_high)} <= {fmt(pm_high)}")
    elif check_intra and intra_h and intra_h > pre_high * (1 + config.MAX_INTRA_BREAKOUT):
        limit = pre_high * (1 + config.MAX_INTRA_BREAKOUT)
        print(f"    ❌ INTRA пробил PRE хай > 10%: {fmt(intra_h)} > {fmt(limit)}")
    else:
        print(f"    ✅ ПРОХОДИТ!")

    print(f"\n  {'='*60}\n")


def main() -> None:
    print("\n" + "=" * 68)
    print("  Pump Screener — Блоки A / B / C  |  small-cap overnight pumps")
    print("=" * 68)

    while True:
        today      = datetime.date.today()
        yesterday  = prev_trading_day(today)
        day_before = prev_trading_day(yesterday)

        print(f"\n  [1] Сегодня   — постмаркет {yesterday}  ->  {today}")
        print(f"  [2] Вчера     — постмаркет {day_before} ->  {yesterday}")
        print(f"  [3] Свои даты")
        print(f"  [4] Проверить тикер")
        print(f"  [0] Выход\n")

        choice = input("  Выбор: ").strip()

        if choice == "1":
            run_screener(yesterday.isoformat(), today.isoformat(), is_today=True)

        elif choice == "2":
            run_screener(day_before.isoformat(), yesterday.isoformat())

        elif choice == "3":
            d1 = input("  Дата постмаркета  (YYYY-MM-DD): ").strip()
            d2 = input("  Следующий день    (YYYY-MM-DD): ").strip()
            run_screener(d1, d2)

        elif choice == "4":
            ticker = input("  Тикер: ").strip().upper()
            print(f"\n  Режим проверки:")
            print(f"  [1] Сегодня   — постмаркет {yesterday}  ->  {today}")
            print(f"  [2] Вчера     — постмаркет {day_before} ->  {yesterday}")
            print(f"  [3] Свои даты")
            sub = input("  Выбор: ").strip()
            if sub == "1":
                analyze_ticker(ticker, yesterday.isoformat(), today.isoformat(), is_today=True)
            elif sub == "2":
                analyze_ticker(ticker, day_before.isoformat(), yesterday.isoformat())
            elif sub == "3":
                d1 = input("  Дата постмаркета  (YYYY-MM-DD): ").strip()
                d2 = input("  Следующий день    (YYYY-MM-DD): ").strip()
                analyze_ticker(ticker, d1, d2)

        elif choice == "0":
            print("\n  Выход.\n")
            break
        else:
            print("  Неверный выбор.")

        input("\n  Нажмите Enter для возврата в меню...")
