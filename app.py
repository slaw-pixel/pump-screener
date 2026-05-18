"""Streamlit web UI for Pump Screener."""
import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
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

run_btn = c_btn.button("🔍 Запустить", width="stretch", type="primary")
st.divider()


# ── Chart ─────────────────────────────────────────────────────
def _resample(df: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    if df.empty or len(df) < 2:
        return df
    agg = (
        df.set_index("ts").sort_index()
        .resample(f"{minutes}min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min",
              "close": "last", "volume": "sum"})
        .dropna(subset=["open"])
        .reset_index()
    )
    return agg


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
                pm_date: str, next_date: str,
                float_shares: float | None = None) -> go.Figure:
    df_pm = _to_df(bars_pm)
    df_nx = _to_df(bars_nx)

    def seg(df: pd.DataFrame, m0: int, m1: int) -> pd.DataFrame:
        return df[(df.minutes >= m0) & (df.minutes < m1)]

    pm_bars  = seg(df_pm, 16*60,   20*60)
    pre_bars = seg(df_nx, 4*60,    9*60+30)
    intra    = seg(df_nx, 9*60+30, 16*60)

    all_bars = pd.concat([pm_bars, pre_bars, intra])
    if all_bars.empty:
        return go.Figure()

    post_r  = _resample(pm_bars)
    pre_r   = _resample(pre_bars)
    intra_r = _resample(intra)
    all_r   = pd.concat([post_r, pre_r, intra_r])
    if all_r.empty:
        return go.Figure()

    def _dt(date_str: str, hour: int, minute: int) -> datetime.datetime:
        d = datetime.date.fromisoformat(date_str)
        return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)

    vol_colors = ["#7ec8c2" if c >= o else "#f0918e"
                  for o, c in zip(all_r["open"], all_r["close"])]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.02,
    )

    # Session background shading — use actual bar timestamps as boundaries
    # because add_vrect with fixed times breaks when rangebreaks compress the axis.
    # add_shape(yref="paper") spans both subplots in one call.
    GRAY_BG = "rgba(180,180,180,0.22)"
    BAR_W   = datetime.timedelta(minutes=15)

    def _shade(x0_dt: datetime.datetime, x1_dt: datetime.datetime, label: str) -> None:
        fig.add_shape(
            type="rect", xref="x", yref="paper",
            x0=x0_dt, x1=x1_dt, y0=0, y1=1,
            fillcolor=GRAY_BG, line_width=0, layer="below",
        )
        fig.add_annotation(
            x=x0_dt, y=0.98, xref="x", yref="paper",
            text=label, showarrow=False,
            xanchor="left", yanchor="top",
            font=dict(color="#555", size=10),
        )

    def _sep(x_val: datetime.datetime) -> None:
        fig.add_shape(
            type="line", xref="x", yref="paper",
            x0=x_val, x1=x_val, y0=0, y1=1,
            line=dict(color="#888888", width=1), opacity=0.6,
        )

    if not post_r.empty:
        p0 = post_r["ts"].iloc[0]
        p1 = post_r["ts"].iloc[-1] + BAR_W
        _shade(p0, p1, "POST")
        _sep(p1)

    if not pre_r.empty:
        r0 = pre_r["ts"].iloc[0]
        r1 = pre_r["ts"].iloc[-1] + BAR_W
        _shade(r0, r1, "PRE")
        _sep(r1)
    # Intraday: no shading (white = regular session)

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=all_r["ts"],
        open=all_r["open"], high=all_r["high"],
        low=all_r["low"],   close=all_r["close"],
        name="Price",
        increasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
        decreasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
    ), row=1, col=1)

    # Volume bars
    fig.add_trace(go.Bar(
        x=all_r["ts"], y=all_r["volume"],
        marker_color=vol_colors,
        marker_line_width=0,
        name="Volume",
        showlegend=False,
    ), row=2, col=1)

    # Volume totals per session — annotations on volume subplot
    max_vol = all_r["volume"].max() if not all_r.empty else 1
    for raw_df, resampled_df, color in [
        (pm_bars,  post_r,  "#b36b00"),
        (pre_bars, pre_r,   "#0277bd"),
        (intra,    intra_r, "#2d6a2d"),
    ]:
        if resampled_df.empty or raw_df.empty:
            continue
        total = raw_df["volume"].sum()
        if total <= 0:
            continue
        mid_ts = resampled_df["ts"].iloc[len(resampled_df) // 2]
        fig.add_annotation(
            x=mid_ts, y=max_vol,
            xref="x", yref="y2",
            text=fmt_vol(total),
            showarrow=False, yanchor="top",
            font=dict(color=color, size=9),
            bgcolor="rgba(255,255,255,0.75)", borderpad=2,
        )

    # Float cumsum marker — purple dotted line where cumulative volume crosses float
    if float_shares and float_shares > 0:
        cumvol, float_ts = 0.0, None
        for _, bar_row in all_bars.sort_values("ts").iterrows():
            cumvol += bar_row["volume"]
            if cumvol >= float_shares:
                float_ts = bar_row["ts"]
                break
        if float_ts is not None:
            fig.add_shape(
                type="line", xref="x", yref="paper",
                x0=float_ts, x1=float_ts, y0=0, y1=1,
                line=dict(color="#9c27b0", width=1.5, dash="dot"),
                opacity=0.85,
            )
            fig.add_annotation(
                x=float_ts, y=max_vol,
                xref="x", yref="y2",
                text="1×Float",
                showarrow=False, yanchor="top",
                font=dict(color="#9c27b0", size=9),
                bgcolor="rgba(255,255,255,0.8)", borderpad=2,
            )

    # Reference lines
    for level, label, color in [
        (r.get("pm_high"),  "POST High", "#b36b00"),
        (r.get("pre_high"), "PRE High",  "#0277bd"),
    ]:
        if level:
            fig.add_hline(
                y=level, line_dash="dash", line_color=color,
                line_width=1.5, opacity=0.8,
                annotation_text=f"{label} {level:.2f}",
                annotation_position="right",
                annotation_font=dict(color=color, size=11),
                row=1, col=1,
            )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=360,
        margin=dict(l=0, r=80, t=10, b=0),
        legend=dict(visible=False),
        plot_bgcolor="white",
        paper_bgcolor="#ffffff",
        xaxis2=dict(gridcolor="#ebebeb"),
        yaxis=dict(gridcolor="#ebebeb"),
        yaxis2=dict(gridcolor="#ebebeb", tickformat=".2s"),
    )
    rangebreaks = [dict(bounds=["sat","mon"]), dict(bounds=[20, 4], pattern="hour")]
    fig.update_xaxes(rangebreaks=rangebreaks)
    return fig


# ── Render single ticker card ─────────────────────────────────
def _high_at_badge(r: dict) -> str:
    pre_h = r.get("pre_high")
    pm_h  = r.get("pm_high")
    if pre_h and pm_h and pre_h > pm_h:
        return '<span style="background:#cfe2ff;color:#0a58ca;padding:2px 8px;border-radius:4px;font-size:0.8rem;font-weight:600">HighAt=PRE</span>'
    if pm_h:
        return '<span style="background:#fff3cd;color:#856404;padding:2px 8px;border-radius:4px;font-size:0.8rem;font-weight:600">HighAt=POST</span>'
    return ""


def render_ticker(r: dict, bars: dict, pm_date: str, next_date: str) -> None:
    t        = r["ticker"]
    earnings = r.get("has_earnings", False)
    border   = "2px solid #f0c000" if earnings else "1px solid #e0e0e0"
    bg       = "rgba(255,200,0,0.06)" if earnings else "transparent"

    tv = f"https://www.tradingview.com/chart/?symbol={t}"
    fv = f"https://finviz.com/quote.ashx?t={t}"

    def v(key, fmt_fn):
        val = r.get(key)
        return fmt_fn(val) if val is not None else "—"

    pm_move  = v("pm_move",  lambda x: f"{x:.1f}%")
    gap      = v("gap",      lambda x: f"{x:.1f}%")
    pre_move = v("pre_move", lambda x: f"{x:.1f}%")
    close_   = v("reg_close",lambda x: f"${x:.2f}")
    flt      = fmt_vol(r.get("float_shares"))
    pm_vol   = fmt_vol(r.get("pm_vol"))
    pre_vol  = fmt_vol(r.get("pre_vol"))
    pre_flow = fmt_vol(r.get("pre_flow"))
    intra15  = fmt_vol(r.get("intra_vol_15"))

    earn_tag   = "&nbsp;🟡 <b>Earnings</b>" if earnings else ""
    badge      = _high_at_badge(r)
    post_c     = "#c47d10" if r.get("pm_move")  else "#888"
    pre_c      = "#0277bd" if r.get("pre_move") else "#888"

    info_html = f"""
<div style="border:{border};border-radius:8px;padding:10px 14px;
            margin-bottom:10px;background:{bg};font-size:0.88rem;line-height:1.6">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
    <a href="{tv}" target="_blank"
       style="font-size:1.25rem;font-weight:700;text-decoration:none;color:inherit">{t}</a>
    {badge}{earn_tag}
    <span style="margin-left:auto;font-size:0.78rem;white-space:nowrap">
      <a href="{tv}" target="_blank" style="text-decoration:none">TV</a> &nbsp;
      <a href="{fv}" target="_blank" style="text-decoration:none">FV</a>
    </span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 12px">
    <span>Close &nbsp;<b>{close_}</b></span>
    <span>Float &nbsp;<b>{flt}</b></span>
    <span style="color:{post_c}">POST High &nbsp;<b>{pm_move}</b></span>
    <span>Gap &nbsp;<b>{gap}</b></span>
    <span style="color:{pre_c}">PRE High &nbsp;<b>{pre_move}</b></span>
    <span></span>
  </div>
  <div style="border-top:1px solid #eee;margin:5px 0"></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 12px">
    <span>POST Vol &nbsp;<b>{pm_vol}</b></span>
    <span>PRE Vol &nbsp;<b>{pre_vol}</b></span>
    <span>PRE Flow &nbsp;<b>{pre_flow}</b></span>
    <span>INTRA&lt;15 &nbsp;<b>{intra15}</b></span>
  </div>
</div>
"""

    col_info, col_chart = st.columns([1, 2.4])

    with col_info:
        st.html(info_html)

    with col_chart:
        if t in bars:
            fig = build_chart(bars[t][0], bars[t][1], r, pm_date, next_date,
                              float_shares=r.get("float_shares"))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("Нет данных для графика.")


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
    if total == 0:
        st.info("По заданным параметрам тикеров не найдено.")
        return

    # Sort by high_time ascending (chronological order of when high was set)
    all_rows.sort(key=lambda r: r.get("high_time") or datetime.datetime.max.replace(tzinfo=UTC))

    earnings_rows = [r for r in all_rows if r.get("has_earnings")]
    other_rows    = [r for r in all_rows if not r.get("has_earnings")]

    st.divider()
    if earnings_rows:
        st.markdown("### 🟡 На репорте")
        for r in earnings_rows:
            render_ticker(r, bars, pm_d, nx_d)
        if other_rows:
            st.divider()
    for r in other_rows:
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
