"""Streamlit web UI for Pump Screener."""
import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from zoneinfo import ZoneInfo

from pump_screener.client import prev_trading_day
from pump_screener.screener import screen as run_screen
from pump_screener.sessions import fmt_vol

UTC = datetime.timezone.utc
ET  = ZoneInfo("America/New_York")

st.set_page_config(
    page_title="Pump Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="metric-container"] { background: #1e1e2e; border-radius: 8px; padding: 12px 16px; }
    .stTabs [data-baseweb="tab"]     { font-size: 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Pump Screener")
    st.divider()

    today      = datetime.date.today()
    yesterday  = prev_trading_day(today)
    day_before = prev_trading_day(yesterday)

    mode = st.radio("Период", ["Сегодня", "Вчера", "Свои даты"], index=0)

    if mode == "Сегодня":
        pm_date   = yesterday.isoformat()
        next_date = today.isoformat()
        is_today  = True
    elif mode == "Вчера":
        pm_date   = day_before.isoformat()
        next_date = yesterday.isoformat()
        is_today  = False
    else:
        col1, col2 = st.columns(2)
        d1 = col1.date_input("Постмаркет",     value=yesterday)
        d2 = col2.date_input("Следующий день", value=today)
        pm_date   = d1.isoformat()
        next_date = d2.isoformat()
        is_today  = (d2 == today)

    st.caption(f"PM: {pm_date}  →  {next_date}")
    st.divider()
    run_btn = st.button("🔍 Запустить скан", use_container_width=True, type="primary")


# ── Chart ─────────────────────────────────────────────────────
def _to_df(bars: list) -> pd.DataFrame:
    rows = []
    for b in bars:
        ts = datetime.datetime.fromtimestamp(b.timestamp / 1000, tz=UTC).astimezone(ET)
        rows.append({
            "ts":      ts,
            "open":    b.open,
            "high":    b.high,
            "low":     b.low,
            "close":   b.close,
            "volume":  getattr(b, "volume", 0) or 0,
            "minutes": ts.hour * 60 + ts.minute,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ts", "open", "high", "low", "close", "volume", "minutes"]
    )


def build_chart(bars_pm: list, bars_nx: list, r: dict) -> go.Figure:
    df_pm = _to_df(bars_pm)
    df_nx = _to_df(bars_nx)

    def seg(df: pd.DataFrame, m0: int, m1: int) -> pd.DataFrame:
        return df[(df.minutes >= m0) & (df.minutes < m1)]

    reg_tail = seg(df_pm, 9*60+30, 16*60).tail(90)
    pm_bars  = seg(df_pm, 16*60,   20*60)
    pre_bars = seg(df_nx, 4*60,    9*60+30)
    intra    = seg(df_nx, 9*60+30, 16*60)

    fig = go.Figure()

    def add(df, name, inc, dec, opacity=1.0):
        if df.empty:
            return
        fig.add_trace(go.Candlestick(
            x=df["ts"],
            open=df["open"], high=df["high"],
            low=df["low"],   close=df["close"],
            name=name,
            increasing=dict(line=dict(color=inc, width=1), fillcolor=inc),
            decreasing=dict(line=dict(color=dec, width=1), fillcolor=dec),
            opacity=opacity,
        ))

    add(reg_tail, "Regular", "#4a4a6a", "#3a3a5a", opacity=0.5)
    add(pm_bars,  "PM",      "#f5a623", "#c47d10")
    add(pre_bars, "PRE",     "#4fc3f7", "#0288d1")
    add(intra,    "Intraday","#66bb6a", "#e53935")

    # Horizontal reference lines
    for level, label, color in [
        (r.get("pm_high"),  "PM High",  "#f5a623"),
        (r.get("pre_high"), "PRE High", "#4fc3f7"),
    ]:
        if level:
            fig.add_hline(
                y=level, line_dash="dot", line_color=color, opacity=0.6,
                annotation_text=f"{label} {level:.2f}",
                annotation_position="right",
            )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=60, t=20, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
    )
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),
            dict(bounds=[20, 4], pattern="hour"),
        ]
    )
    return fig


# ── Results ───────────────────────────────────────────────────
BLOCK_META = {
    "A": ("🟡 Блок A", f"PM pump — хай не переписан в PRE и интрадей"),
    "B": ("🔵 Блок B", "PRE pump — без предшествующего PM мува"),
    "C": ("🟢 Блок C", "PM pump + продолжение в PRE"),
}


def render(result: dict) -> None:
    meta   = result["meta"]
    blocks = result["blocks"]
    bars   = result["bars"]

    # ── Header metrics
    st.markdown(f"### Постмаркет: **{meta['pm_date']}** → **{meta['next_date']}**")

    total = sum(len(v) for v in blocks.values())
    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Всего найдено", total)
    c1.metric("🟡 Блок A", len(blocks["A"]))
    c2.metric("🔵 Блок B", len(blocks["B"]))
    c3.metric("🟢 Блок C", len(blocks["C"]))

    st.divider()

    if total == 0:
        st.info("По заданным параметрам тикеров не найдено.")
        return

    tab_labels = [f"{BLOCK_META[b][0]} ({len(blocks[b])})" for b in ("A", "B", "C")]
    tabs = st.tabs(tab_labels)

    for tab, block_id in zip(tabs, ("A", "B", "C")):
        with tab:
            rows = blocks[block_id]
            st.caption(BLOCK_META[block_id][1])

            if not rows:
                st.info("Нет тикеров.")
                continue

            # ── Summary table
            df = pd.DataFrame([{
                "Ticker":         r["ticker"],
                "PM Move%":       r["pm_move"],
                "Gap%":           r["gap"],
                "PRE Move%":      r["pre_move"],
                "PM Vol":         fmt_vol(r["pm_vol"]),
                "PRE Vol":        fmt_vol(r["pre_vol"]),
                "INTRA до 15:00": fmt_vol(r["intra_vol_15"]),
                "PRE Flow":       fmt_vol(r["pre_flow"]),
            } for r in rows])

            def _fmt_pct(v):
                return f"{v:.1f}%" if v is not None else "—"

            styled = (
                df.style
                .format({
                    "PM Move%":  _fmt_pct,
                    "Gap%":      _fmt_pct,
                    "PRE Move%": _fmt_pct,
                })
                .background_gradient(subset=["PM Move%"],  cmap="YlOrRd", vmin=0,  vmax=200)
                .background_gradient(subset=["PRE Move%"], cmap="Blues",  vmin=0,  vmax=200)
                .background_gradient(subset=["Gap%"],      cmap="Greens", vmin=0,  vmax=100)
            )

            st.dataframe(
                styled,
                use_container_width=True,
                hide_index=True,
                height=min(45 + len(rows) * 38, 420),
            )

            # ── Per-ticker chart + stats
            st.markdown("---")
            for r in rows:
                t = r["ticker"]
                label = f"📊 {t}  —  {r['move_info'] or ''}"
                with st.expander(label):
                    tv_url = f"https://www.tradingview.com/chart/?symbol={t}"
                    fv_url = f"https://finviz.com/quote.ashx?t={t}"
                    st.markdown(
                        f"[TradingView]({tv_url}) &nbsp;|&nbsp; [Finviz]({fv_url})",
                        unsafe_allow_html=True,
                    )

                    if t in bars:
                        fig = build_chart(bars[t][0], bars[t][1], r)
                        st.plotly_chart(fig, use_container_width=True)

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("PM Move",   f"{r['pm_move']:.1f}%"  if r["pm_move"]  else "—")
                    m2.metric("Gap",       f"{r['gap']:.1f}%"      if r["gap"]      else "—")
                    m3.metric("PRE Move",  f"{r['pre_move']:.1f}%" if r["pre_move"] else "—")
                    m4.metric("PRE Flow",  fmt_vol(r["pre_flow"]))
                    m5.metric("PRE Close", f"${r['reg_close']:.2f}" if r["reg_close"] else "—")


# ── Main ──────────────────────────────────────────────────────
if run_btn:
    with st.status("Запускаю скан...", expanded=True) as status:
        progress = st.progress(0.0)

        def on_progress(stage: str, value: float) -> None:
            if stage == "snapshots":
                status.write("📡 Загружаю snapshots...")
                progress.progress(value * 0.2)
            elif stage == "fetching":
                status.write(f"📊 Загружаю минутные бары... {value:.0%}")
                progress.progress(0.2 + value * 0.8)

        result = run_screen(pm_date, next_date, is_today=is_today, on_progress=on_progress)

        total = sum(len(v) for v in result["blocks"].values())
        status.update(
            label=f"✅ Готово — найдено {total} тикеров",
            state="complete",
            expanded=False,
        )
        progress.empty()
        st.session_state["result"] = result

if "result" in st.session_state:
    render(st.session_state["result"])
else:
    st.markdown("## 📈 Pump Screener")
    st.info("Выберите период в боковой панели и нажмите **Запустить скан**.")
