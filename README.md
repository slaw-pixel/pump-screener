# pump-screener

**Small-cap overnight pump scanner** — detects stocks (market cap ≤ $300M) with significant after-hours or pre-market moves where the high has not yet been reclaimed in the regular session. Data via [Polygon.io](https://polygon.io) (Massive.com) minute bars.

---

## How it works

The screener fetches minute bars for two consecutive trading days and classifies tickers into three blocks based on where the initial move occurred and whether the high has been reclaimed.

### Block A — After-hours pump, high intact

| Condition | Value |
|-----------|-------|
| After-hours move from regular close | ≥ +40% |
| Pre-market does **not** exceed PM high | ✓ |
| Intraday does not exceed PM high by more than | +10% |
| Pre-market money flow | ≥ $2M |

The stock surged after-hours. Next day it opens with a gap but trades below the PM high — potential setup.

### Block B — Pre-market pump, no prior PM move

| Condition | Value |
|-----------|-------|
| Pre-market move from regular close | ≥ +30% |
| After-hours move | < 30% (move originated in PRE) |
| Intraday does not exceed PRE high by more than | +10% |

Catalyst hit overnight or early morning; the high was set in pre-market and has not been broken intraday.

### Block C — PM pump + PRE continuation

| Condition | Value |
|-----------|-------|
| After-hours move from regular close | ≥ +30% |
| Pre-market **exceeds** the PM high | ✓ |
| Intraday does not exceed PRE high by more than | +10% |

Strong two-session momentum: after-hours pump followed by pre-market continuation.

---

## Setup

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/) (recommended)

```bash
git clone https://github.com/slaw-pixel/pump-screener.git
cd pump-screener

# install dependencies
uv sync          # or: pip install -e .

# configure API key
cp .env.example .env
# edit .env → POLYGON_API_KEY=your_key_here
```

Get your API key at [massive.com](https://massive.com) or [polygon.io](https://polygon.io).

---

## Usage

```bash
uv run pump-screener
```

```
════════════════════════════════════════════════════════════════════
  Pump Screener — Блоки A / B / C  |  small-cap overnight pumps
════════════════════════════════════════════════════════════════════

  [1] Сегодня   — постмаркет 2025-01-22  ->  2025-01-23
  [2] Вчера     — постмаркет 2025-01-21  ->  2025-01-22
  [3] Свои даты
  [4] Проверить тикер
  [0] Выход
```

Option **[4]** runs a detailed breakdown for a single ticker — shows each session's highs/volumes and whether it passes or fails each block with the exact rejection reason.

### Sample output

```
════════════════════════════════════════════════════════════════════════
  БЛОК A — PM +40.0%, хай не переписан  |  Найдено: 2
════════════════════════════════════════════════════════════════════════
  ROLR     InitialMov=PM(132.5%)  HighAt=PRE
  CMND     InitialMov=PM(64.1%)   HighAt=PRE
  ────────────────────────────────────────────────────────────────────
```

---

## Configuration

All thresholds are in [`pump_screener/config.py`](pump_screener/config.py):

| Constant | Default | Description |
|----------|---------|-------------|
| `MIN_POST_MOVE_PCT_A` | 40.0 | Block A: min after-hours move (%) |
| `MIN_POST_MOVE_PCT_C` | 30.0 | Block C: min after-hours move (%) |
| `MIN_PRE_MOVE_PCT_B`  | 30.0 | Block B: min pre-market move (%) |
| `MIN_PRICE`           | 0.50 | Min stock price |
| `MAX_PRICE`           | 100.0 | Max stock price |
| `MAX_MARKET_CAP`      | 300M | Max market cap ($) |
| `MIN_VOLUME`          | 100K | Min daily volume (snapshot pre-filter) |
| `MAX_INTRA_BREAKOUT`  | 0.10 | Intraday may exceed high by max 10% |
| `MIN_PREMKT_FLOW`     | 2M   | Min pre-market money flow ($) |
| `EXTRA_TICKERS`       | []   | Manually added tickers |

---

## Project structure

```
pump-screener/
├── pump_screener/
│   ├── config.py     # all thresholds and settings
│   ├── client.py     # Polygon.io API wrapper + ticker cache
│   ├── sessions.py   # minute-bar session parsing + helpers
│   ├── screener.py   # block A/B/C classification + full scan
│   └── cli.py        # interactive menu + single-ticker analysis
├── .env.example
└── pyproject.toml
```

---

---

## RU — Документация

### Описание

Скринер малокапитализированных акций (маркеткап ≤ $300M) для поиска торговых ситуаций на основе движений постмаркета и премаркета. Данные — минутные бары через API Polygon.io (Massive.com).

### Три торговых блока

**Блок A — Постмаркет pump, хай не переписан**

Акция резко выросла в постмаркете. На следующий день открывается с гэпом вверх, но торгуется ниже постмаркетного хая и выше $2M денежного потока в премаркете.

**Блок B — Премаркет pump, без предшествующего PM мува**

Катализатор вышел ночью или рано утром. Мув начался в премаркете, хай ещё не переписан в основной сессии.

**Блок C — Постмаркет pump + продолжение в премаркете**

Мув начался в постмаркете, затем продолжился в премаркете — двухсессионный импульс.

### Временны́е зоны

Все сессии определяются по **America/New_York** (корректно для EST и EDT):

| Сессия | Время ET |
|--------|----------|
| PRE (премаркет) | 04:00 — 09:29 |
| INTRA (основная) | 09:30 — 15:59 |
| PM (постмаркет) | 16:00 — 19:59 |

### Установка и запуск

```bash
git clone https://github.com/slaw-pixel/pump-screener.git
cd pump-screener
uv sync
cp .env.example .env   # вставить API ключ
uv run pump-screener
```

### Кэш тикеров

При первом запуске скрипт загружает все CS-акции с API и сохраняет в `ticker_cache.txt`. Кэш обновляется раз в 24 часа автоматически.

---

## License

MIT
