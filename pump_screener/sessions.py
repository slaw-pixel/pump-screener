"""Session parsing and formatting helpers."""
import datetime
from typing import TypedDict
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


class SessionData(TypedDict):
    regular_close:   float | None
    intra_open:      float | None
    pm_high:         float | None
    pm_volume:       float
    pre_high:        float | None
    pre_volume:      float
    pre_moneyflow:   float
    intra_high:      float | None
    intra_volume:    float
    intra_volume_15: float   # intraday volume 09:30–15:00 only


def parse_sessions(
    bars: list,
    cutoff_utc: datetime.datetime | None = None,
) -> SessionData:
    """Split minute bars into PM / PRE / INTRA buckets and compute session stats.

    Uses America/New_York to handle both EST (UTC-5) and EDT (UTC-4) correctly.
    """
    pm: list = []
    pre: list = []
    intra: list = []

    for bar in bars:
        ts = datetime.datetime.fromtimestamp(bar.timestamp / 1000, tz=datetime.timezone.utc)
        if cutoff_utc and ts > cutoff_utc:
            continue
        et = ts.astimezone(ET)
        minutes = et.hour * 60 + et.minute
        if 16 * 60 <= minutes < 20 * 60:
            pm.append(bar)
        elif 4 * 60 <= minutes < 9 * 60 + 30:
            pre.append(bar)
        elif 9 * 60 + 30 <= minutes < 16 * 60:
            intra.append(bar)

    intra_15 = [b for b in intra if (
        datetime.datetime.fromtimestamp(b.timestamp / 1000, tz=datetime.timezone.utc)
        .astimezone(ET).hour * 60
        + datetime.datetime.fromtimestamp(b.timestamp / 1000, tz=datetime.timezone.utc)
        .astimezone(ET).minute
    ) < 15 * 60]

    return {
        "regular_close":   intra[-1].close                                          if intra    else None,
        "intra_open":      intra[0].open                                            if intra    else None,
        "pm_high":         max(b.high for b in pm)                                  if pm       else None,
        "pm_volume":       sum(b.volume for b in pm if b.volume)                    if pm       else 0.0,
        "pre_high":        max(b.high for b in pre)                                 if pre      else None,
        "pre_volume":      sum(b.volume for b in pre if b.volume)                   if pre      else 0.0,
        "pre_moneyflow":   sum(b.volume * b.vwap for b in pre if b.volume and b.vwap) if pre   else 0.0,
        "intra_high":      max(b.high for b in intra)                               if intra    else None,
        "intra_volume":    sum(b.volume for b in intra if b.volume)                 if intra    else 0.0,
        "intra_volume_15": sum(b.volume for b in intra_15 if b.volume)              if intra_15 else 0.0,
    }


# ── Formatting helpers ────────────────────────────────────────

def pct(a: float | None, b: float | None) -> float | None:
    if a and b and b > 0:
        return round((a - b) / b * 100, 2)
    return None


def fmt(v: float | None, decimals: int = 2) -> str:
    return f"{v:.{decimals}f}" if v is not None else "---"


def fmt_vol(v: float | None) -> str:
    if not v:
        return "---"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return str(int(v))


def initial_move_label(
    pm_high: float | None,
    pre_high: float | None,
    reg_close: float | None,
) -> str:
    pm_move  = pct(pm_high,  reg_close)
    pre_move = pct(pre_high, reg_close)
    if pm_move and pm_move >= 30:
        if pre_high and pre_high > pm_high:
            return f"InitialMov=PM({pm_move:.1f}%)  HighAt=PRE({pre_move:.1f}%)"
        return f"InitialMov=PM({pm_move:.1f}%)  HighAt=PM"
    if pre_move and pre_move >= 30:
        return f"InitialMov=PRE({pre_move:.1f}%)  HighAt=PRE"
    return ""
