"""Session parsing and formatting helpers."""
import datetime
from typing import TypedDict
from zoneinfo import ZoneInfo

from . import config

ET = ZoneInfo("America/New_York")


class SessionData(TypedDict):
    regular_close:   float | None
    intra_open:      float | None
    pm_high:         float | None
    pm_high_time:    datetime.datetime | None
    pm_volume:       float
    pre_high:        float | None
    pre_high_time:   datetime.datetime | None
    pre_volume:      float
    pre_moneyflow:   float
    intra_high:      float | None
    early_high:      float | None              # intraday high 9:30 → HIGH_CUTOFF
    early_high_time: datetime.datetime | None
    late_high:       float | None              # intraday high HIGH_CUTOFF → 16:00
    intra_volume:    float
    intra_volume_15: float


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

    def _minutes(bar) -> int:
        et = _bar_time(bar)
        return et.hour * 60 + et.minute

    def _bar_time(bar) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(
            bar.timestamp / 1000, tz=datetime.timezone.utc
        ).astimezone(ET)

    cutoff_min = config.HIGH_CUTOFF_HOUR * 60 + config.HIGH_CUTOFF_MINUTE
    early = [b for b in intra if _minutes(b) < cutoff_min]
    late  = [b for b in intra if _minutes(b) >= cutoff_min]
    early_high_bar = max(early, key=lambda b: b.high) if early else None

    pm_high_bar  = max(pm,  key=lambda b: b.high) if pm  else None
    pre_high_bar = max(pre, key=lambda b: b.high) if pre else None

    return {
        "regular_close":   intra[-1].close                                            if intra    else None,
        "intra_open":      intra[0].open                                              if intra    else None,
        "pm_high":         pm_high_bar.high                                           if pm_high_bar  else None,
        "pm_high_time":    _bar_time(pm_high_bar)                                     if pm_high_bar  else None,
        "pm_volume":       sum(b.volume for b in pm if b.volume)                      if pm       else 0.0,
        "pre_high":        pre_high_bar.high                                          if pre_high_bar else None,
        "pre_high_time":   _bar_time(pre_high_bar)                                    if pre_high_bar else None,
        "pre_volume":      sum(b.volume for b in pre if b.volume)                     if pre      else 0.0,
        "pre_moneyflow":   sum(b.volume * b.vwap for b in pre if b.volume and b.vwap) if pre     else 0.0,
        "intra_high":      max(b.high for b in intra)                                 if intra    else None,
        "early_high":      early_high_bar.high                                        if early_high_bar else None,
        "early_high_time": _bar_time(early_high_bar)                                  if early_high_bar else None,
        "late_high":       max(b.high for b in late)                                  if late     else None,
        "intra_volume":    sum(b.volume for b in intra if b.volume)                   if intra    else 0.0,
        "intra_volume_15": sum(b.volume for b in intra_15 if b.volume)                if intra_15 else 0.0,
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


def high_at(
    pm_high: float | None,
    pre_high: float | None,
    early_high: float | None = None,
) -> str | None:
    """Session where the overall high (up to HIGH_CUTOFF) was set: PM / PRE / INTRA."""
    cands = [(v, lbl) for v, lbl in [(pm_high, "PM"), (pre_high, "PRE"), (early_high, "INTRA")] if v]
    return max(cands, key=lambda x: x[0])[1] if cands else None


def initial_move_label(
    pm_high: float | None,
    pre_high: float | None,
    reg_close: float | None,
    early_high: float | None = None,
) -> str:
    pm_move  = pct(pm_high,  reg_close)
    pre_move = pct(pre_high, reg_close)
    at = high_at(pm_high, pre_high, early_high)
    at_move = pct({"PM": pm_high, "PRE": pre_high, "INTRA": early_high}.get(at or ""), reg_close)
    if pm_move and pm_move >= 30:
        if at == "PM":
            return f"InitialMov=PM({pm_move:.1f}%)  HighAt=PM"
        return f"InitialMov=PM({pm_move:.1f}%)  HighAt={at}({at_move:.1f}%)"
    if pre_move and pre_move >= 30:
        if at == "PRE":
            return f"InitialMov=PRE({pre_move:.1f}%)  HighAt=PRE"
        return f"InitialMov=PRE({pre_move:.1f}%)  HighAt={at}({at_move:.1f}%)"
    return ""
