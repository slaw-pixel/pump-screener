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
    .ticker-card {
        border: 1px solid #e0e0e0; border-radius: 8px;
        padding: 12px 16px; margin-bottom: 12px;
    }
    .ticker-card-earnings {
        border: 1px solid #f0c000; border-radius: 8px;
        padding: 12px 16px; margin-bottom: 12px;
        background: rgba(255, 200, 0, 0.07);
    }
    .block-badge-A { background:#fff3cd; color:#856404; padding:2px 8px; border-radius:4px; font-weight:600; font-size:0.8rem; }
    .block-badge-B { background:#cfe2ff; color:#0a58ca; padding:2px 8px; border-radius:4px; font-weight:600; font-size:0.8rem; }
    .block-badge-C { background:#d1e7dd; color:#0f5132; padding:2px 8px; border-radius:4px; font-weight:600; font-size:0.8rem; }
</style>
""", unsafe_allow_html=True)

BLOCK_COLOR = {"A": "#856404", "B": "#0a58ca", "C": "#0f5132"}
BLOCK_LABEL = {"A": "Блок A", "B": "Блок B", "C": "Блок C"}

# ── Top controls ──────────────────────────────────────────────
st.markdown("## 📈 Pump Screener")

today      = datetime.date.today()
yesterday  = prev_trading_day(today)
day_before = prev_trading_day(yesterday)

c_mode, c_info, c_d1, c_d2, c_btn = st.columns([1.1, 1.3, 1.1, 1.1, 0.8])

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


# ── Chart ─────────────────────────────────────────────────────
def _to_df(bars: list) -> pd.DataFrame:
    rows = []
    for b in bars:
        ts = datetime.datetime.fromtimestamp(b.timestamp / 1000, tz=UTC).astimezone(ET)
        rows.append({
            "ts":      ts,
            "open":    b.open,  "high":  b.high,
            "low":     b.low,   "close": b.close,
            "minutes": ts.hour * 60 + ts.minute,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ts","open","high","low","close","minutes"])


def build_chart(bars_pm: list, bars_nx: list, r: dict,
                pm_date: str, next_date: str) -> go.Figure:
    df_pm = _to_df(bars_pm)
    df_nx = _to_df(bars_nx)

    def seg(df: pd.DataFrame, m0: int, m1: int) -> pd.DataFrame:
        return df[(df.minutes >= m0) & (df.minutes < m1)]

    # Only show PM + PRE + Intraday (no regular session — too noisy)
    pm_bars  = seg(df_pm, 16*60,   20*60)
    pre_bars = seg(df_nx, 4*60,    9*60+30)
    intra    = seg(df_nx, 9*60+30, 16*60)

    all_bars = pd.concat([pm_bars, pre_bars, intra])
    if all_bars.empty:
        return go.Figure()

    def _dt(date_str: str, hour: int, minute: int) -> datetime.datetime:
        d = datetime.date.fromisoformat(date_str)
        return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)

    fig = go.Figure()

    # Session background bands
    if not pm_bars.empty:
        fig.add_vrect(
            x0=_dt(pm_date, 16, 0), x1=_dt(pm_date, 20, 0),
            fillcolor="rgba(245,166,35,0.10)", line_width=0,
            annotation_text="PM", annotation_position="top left",
            annotation_font=dict(color="#b36b00", size=11),
        )
    if not pre_bars.empty:
        fig.add_vrect(
            x0=_dt(next_date, 4, 0), x1=_dt(next_date, 9, 30),
            fillcolor="rgba(79,195,247,0.10)", line_width=0,
            annotation_text="PRE", annotation_position="top left",
            annotation_font=dict(color="#0277bd", size=11),
        )
    if not intra.empty:
        fig.add_vrect(
            x0=_dt(next_date, 9, 30), x1=_dt(next_date, 16, 0),
            fillcolor="rgba(100,200,100,0.05)", line_width=0,
            annotation_text="Intraday", annotation_position="top left",
            annotation_font=dict(color="#2d6a2d", size=11),
        )

    fig.add_trace(go.Candlestick(
        x=all_bars["ts"],
        open=all_bars["open"], high=all_bars["high"],
        low=all_bars["low"],   close=all_bars["close"],
        name="Price",
        increasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
        decreasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
    ))

    for level, label, color in [
        (r.get("pm_high"),  "PM High",  "#b36b00"),
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
        height=300,
        margin=dict(l=0, r=80, t=10, b=0),
        legend=dict(visible=False),
        plot_bgcolor="#fafafa",
        paper_bgcolor="#ffffff",
        xaxis=dict(gridcolor="#ebebeb"),
        yaxis=dict(gridcolor="#ebebeb"),
    )
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat","mon"]),
            dict(bounds=[20, 4], pattern="hour"),
        ]
    )
    return fig


# ── Render single ticker card ─────────────────────────────────
def render_ticker(r: dict, bars: dict, pm_date: str, next_date: str) -> None:
    t          = r["ticker"]
    earnings   = r.get("has_earnings", False)
    block_id   = r["block"]
    card_class = "ticker-card-earnings" if earnings else "ticker-card"

    st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)

    col_info, col_chart = st.columns([1, 2.2])

    with col_info:
        # Header: ticker + block badge + earnings tag
        badge = f'<span class="block-badge-{block_id}">{BLOCK_LABEL[block_id]}</span>'
        earn_tag = " 🟡 Earnings" if earnings else ""
        tv  = f"https://www.tradingview.com/chart/?symbol={t}"
        fv  = f"https://finviz.com/quote.ashx?t={t}"
        st.markdown(
            f"### [{t}]({tv}) &nbsp; {badge}{earn_tag}",
            unsafe_allow_html=True,
        )
        st.caption(r.get("move_info") or "")
        st.markdown(f"[Finviz]({fv})", unsafe_allow_html=True)

        st.markdown("---")

        def _m(label, val):
            st.markdown(f"**{label}:** {val}")

        _m("Close",          f"${r['reg_close']:.2f}" if r.get("reg_close") else "—")
        _m("PM Move",        f"{r['pm_move']:.1f}%"   if r.get("pm_move")   else "—")
        _m("Gap",            f"{r['gap']:.1f}%"        if r.get("gap")       else "—")
        _m("PRE Move",       f"{r['pre_move']:.1f}%"  if r.get("pre_move")  else "—")
        _m("Float",          fmt_vol(r.get("float_shares")))
        st.markdown("---")
        _m("PM Vol",         fmt_vol(r.get("pm_vol")))
        _m("PRE Vol",        fmt_vol(r.get("pre_vol")))
        _m("PRE Flow",       fmt_vol(r.get("pre_flow")))
        _m("INTRA до 15:00", fmt_vol(r.get("intra_vol_15")))

    with col_chart:
        if t in bars:
            fig = build_chart(bars[t][0], bars[t][1], r, pm_date, next_date)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Нет данных для графика.")

    st.markdown("</div>", unsafe_allow_html=True)


# ── Main render ───────────────────────────────────────────────
def render(result: dict) -> None:
    meta   = result["meta"]
    blocks = result["blocks"]
    bars   = result["bars"]
    pm_d   = meta["pm_date"]
    nx_d   = meta["next_date"]

    st.markdown(f"**Постмаркет:** {pm_d} &nbsp;→&nbsp; **{nx_d}**",
                unsafe_allow_html=True)

    # Merge all blocks into one list, tag each record with its block id
    all_rows = []
    for block_id, rows in blocks.items():
        for r in rows:
            all_rows.append({**r, "block": block_id})

    total = len(all_rows)
    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Найдено всего", total)
    c1.metric("🟡 Блок A", len(blocks["A"]))
    c2.metric("🔵 Блок B", len(blocks["B"]))
    c3.metric("🟢 Блок C", len(blocks["C"]))

    if total == 0:
        st.info("По заданным параметрам тикеров не найдено.")
        return

    # Sort by high_time ascending (chronological order of when high was set)
    all_rows.sort(key=lambda r: r.get("high_time") or datetime.datetime.max.replace(tzinfo=UTC))

    st.divider()
    for r in all_rows:
        render_ticker(r, bars, pm_d, nx_d)


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
