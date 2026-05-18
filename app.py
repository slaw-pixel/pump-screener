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
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.2rem; padding-bottom: 1rem; }
    [data-testid="metric-container"] {
        background: #1a1a2e; border-radius: 8px; padding: 10px 14px;
    }
    .stTabs [data-baseweb="tab"] { font-size: 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Top controls ──────────────────────────────────────────────
st.markdown("## 📈 Pump Screener")

today      = datetime.date.today()
yesterday  = prev_trading_day(today)
day_before = prev_trading_day(yesterday)

c_mode, c_info, c_d1, c_d2, c_btn = st.columns([1.2, 1.4, 1.2, 1.2, 0.9])

mode = c_mode.radio("", ["Сегодня", "Вчера", "Даты"], horizontal=False,
                    label_visibility="collapsed")

if mode == "Сегодня":
    pm_date, next_date, is_today = yesterday.isoformat(), today.isoformat(), True
    c_info.markdown(f"**PM:** {pm_date}<br>**→** {next_date}", unsafe_allow_html=True)
elif mode == "Вчера":
    pm_date, next_date, is_today = day_before.isoformat(), yesterday.isoformat(), False
    c_info.markdown(f"**PM:** {pm_date}<br>**→** {next_date}", unsafe_allow_html=True)
else:
    d1 = c_d1.date_input("Постмаркет",     value=yesterday)
    d2 = c_d2.date_input("Следующий день", value=today)
    pm_date, next_date, is_today = d1.isoformat(), d2.isoformat(), (d2 == today)

run_btn = c_btn.button("🔍 Запустить", use_container_width=True, type="primary")
st.divider()


# ── Color helpers (no matplotlib needed) ─────────────────────
def _cell_color(val: float | None, vmax: float, rgb_hi: tuple) -> str:
    """Light-to-color gradient. Always black text."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    norm = min(max(val / vmax, 0), 1)
    r = int(255 - (255 - rgb_hi[0]) * norm)
    g = int(255 - (255 - rgb_hi[1]) * norm)
    b = int(255 - (255 - rgb_hi[2]) * norm)
    return f"background-color: rgb({r},{g},{b}); color: #000"


def style_table(df: pd.DataFrame):
    def pm_color(v):  return _cell_color(v, 200, (255, 160, 40))
    def pre_color(v): return _cell_color(v, 200, (60,  150, 230))
    def gap_color(v): return _cell_color(v, 100, (60,  180, 80))

    def _fmt(v):
        return f"{v:.1f}%" if v is not None and not pd.isna(v) else "—"

    return (
        df.style
        .format({"PM Move%": _fmt, "Gap%": _fmt, "PRE Move%": _fmt})
        .applymap(pm_color,  subset=["PM Move%"])
        .applymap(pre_color, subset=["PRE Move%"])
        .applymap(gap_color, subset=["Gap%"])
    )


# ── Chart (light background + session bands) ──────────────────
def _to_df(bars: list) -> pd.DataFrame:
    rows = []
    for b in bars:
        ts = datetime.datetime.fromtimestamp(b.timestamp / 1000, tz=UTC).astimezone(ET)
        rows.append({
            "ts":      ts,
            "open":    b.open,  "high":  b.high,
            "low":     b.low,   "close": b.close,
            "volume":  getattr(b, "volume", 0) or 0,
            "minutes": ts.hour * 60 + ts.minute,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ts","open","high","low","close","volume","minutes"])


def build_chart(bars_pm: list, bars_nx: list, r: dict,
                pm_date: str, next_date: str) -> go.Figure:
    df_pm = _to_df(bars_pm)
    df_nx = _to_df(bars_nx)

    def seg(df: pd.DataFrame, m0: int, m1: int) -> pd.DataFrame:
        return df[(df.minutes >= m0) & (df.minutes < m1)]

    reg_tail = seg(df_pm, 9*60+30, 16*60).tail(90)
    pm_bars  = seg(df_pm, 16*60,   20*60)
    pre_bars = seg(df_nx, 4*60,    9*60+30)
    intra    = seg(df_nx, 9*60+30, 16*60)

    all_bars = pd.concat([reg_tail, pm_bars, pre_bars, intra])
    if all_bars.empty:
        return go.Figure()

    fig = go.Figure()

    # Session background bands
    def _dt(date_str: str, hour: int, minute: int) -> datetime.datetime:
        d = datetime.date.fromisoformat(date_str)
        return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)

    if not pm_bars.empty:
        fig.add_vrect(
            x0=_dt(pm_date, 16, 0), x1=_dt(pm_date, 20, 0),
            fillcolor="rgba(245,166,35,0.12)", line_width=0,
            annotation_text="PM", annotation_position="top left",
            annotation_font=dict(color="#c47d10", size=11),
        )
    if not pre_bars.empty:
        fig.add_vrect(
            x0=_dt(next_date, 4, 0), x1=_dt(next_date, 9, 30),
            fillcolor="rgba(79,195,247,0.12)", line_width=0,
            annotation_text="PRE", annotation_position="top left",
            annotation_font=dict(color="#0288d1", size=11),
        )

    # Candlesticks — single trace, standard colors
    fig.add_trace(go.Candlestick(
        x=all_bars["ts"],
        open=all_bars["open"], high=all_bars["high"],
        low=all_bars["low"],   close=all_bars["close"],
        name="Price",
        increasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
        decreasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
    ))

    # Reference lines
    for level, label, color in [
        (r.get("pm_high"),  "PM High",  "#e67e00"),
        (r.get("pre_high"), "PRE High", "#0277bd"),
    ]:
        if level:
            fig.add_hline(
                y=level, line_dash="dash", line_color=color,
                line_width=1.5, opacity=0.8,
                annotation_text=f"{label} {level:.2f}",
                annotation_position="right",
                annotation_font=dict(color=color, size=11),
            )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=380,
        margin=dict(l=0, r=80, t=10, b=0),
        legend=dict(visible=False),
        plot_bgcolor="#fafafa",
        paper_bgcolor="#ffffff",
        xaxis=dict(gridcolor="#e8e8e8", showgrid=True),
        yaxis=dict(gridcolor="#e8e8e8", showgrid=True),
    )
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat","mon"]),
            dict(bounds=[20, 4], pattern="hour"),
        ]
    )
    return fig


# ── Results ───────────────────────────────────────────────────
BLOCK_META = {
    "A": ("🟡 Блок A", "PM pump — хай не переписан в PRE и интрадей"),
    "B": ("🔵 Блок B", "PRE pump — без предшествующего PM мува"),
    "C": ("🟢 Блок C", "PM pump + продолжение в PRE"),
}


def render(result: dict) -> None:
    meta   = result["meta"]
    blocks = result["blocks"]
    bars   = result["bars"]
    pm_d   = meta["pm_date"]
    nx_d   = meta["next_date"]

    st.markdown(f"**Постмаркет:** {pm_d} &nbsp;→&nbsp; **{nx_d}**",
                unsafe_allow_html=True)

    total = sum(len(v) for v in blocks.values())
    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Найдено всего", total)
    c1.metric("🟡 Блок A", len(blocks["A"]))
    c2.metric("🔵 Блок B", len(blocks["B"]))
    c3.metric("🟢 Блок C", len(blocks["C"]))

    st.divider()

    if total == 0:
        st.info("По заданным параметрам тикеров не найдено.")
        return

    tab_labels = [f"{BLOCK_META[b][0]} ({len(blocks[b])})" for b in ("A","B","C")]
    tabs = st.tabs(tab_labels)

    for tab, block_id in zip(tabs, ("A","B","C")):
        with tab:
            rows = blocks[block_id]
            st.caption(BLOCK_META[block_id][1])

            if not rows:
                st.info("Нет тикеров.")
                continue

            df = pd.DataFrame([{
                "Ticker":         r["ticker"],
                "Float":          fmt_vol(r.get("float_shares")),
                "PM Move%":       r["pm_move"],
                "Gap%":           r["gap"],
                "PRE Move%":      r["pre_move"],
                "PM Vol":         fmt_vol(r["pm_vol"]),
                "PRE Vol":        fmt_vol(r["pre_vol"]),
                "INTRA до 15:00": fmt_vol(r["intra_vol_15"]),
                "PRE Flow":       fmt_vol(r["pre_flow"]),
            } for r in rows])

            st.dataframe(
                style_table(df),
                use_container_width=True,
                hide_index=True,
                height=min(45 + len(rows) * 38, 420),
            )

            st.markdown("---")
            for r in rows:
                t = r["ticker"]
                with st.expander(f"📊 {t}  —  {r['move_info'] or ''}"):
                    tv = f"https://www.tradingview.com/chart/?symbol={t}"
                    fv = f"https://finviz.com/quote.ashx?t={t}"
                    st.markdown(f"[TradingView]({tv}) &nbsp;|&nbsp; [Finviz]({fv})",
                                unsafe_allow_html=True)

                    if t in bars:
                        fig = build_chart(bars[t][0], bars[t][1], r, pm_d, nx_d)
                        st.plotly_chart(fig, use_container_width=True)

                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("PM Move",  f"{r['pm_move']:.1f}%"  if r["pm_move"]  else "—")
                    m2.metric("Gap",      f"{r['gap']:.1f}%"      if r["gap"]      else "—")
                    m3.metric("PRE Move", f"{r['pre_move']:.1f}%" if r["pre_move"] else "—")
                    m4.metric("PRE Flow", fmt_vol(r["pre_flow"]))
                    m5.metric("Close",    f"${r['reg_close']:.2f}" if r["reg_close"] else "—")
                    m6.metric("Float",    fmt_vol(r.get("float_shares")))


# ── Run ───────────────────────────────────────────────────────
if run_btn:
    with st.status("Запускаю скан...", expanded=True) as status:
        progress = st.progress(0.0)
        msg = st.empty()

        def on_progress(stage: str, value: float) -> None:
            if stage == "snapshots":
                msg.markdown("📡 Загружаю snapshots...")
                progress.progress(0.1)
            elif stage == "fetching":
                msg.markdown(f"📊 Загружаю бары... **{value:.0%}**")
                progress.progress(0.2 + value * 0.8)

        result = run_screen(pm_date, next_date, is_today=is_today, on_progress=on_progress)
        total  = sum(len(v) for v in result["blocks"].values())
        status.update(label=f"✅ Готово — найдено {total} тикеров",
                      state="complete", expanded=False)
        progress.empty()
        msg.empty()
        st.session_state["result"] = result

if "result" in st.session_state:
    render(st.session_state["result"])
else:
    st.info("Выберите период и нажмите **🔍 Запустить**.")
