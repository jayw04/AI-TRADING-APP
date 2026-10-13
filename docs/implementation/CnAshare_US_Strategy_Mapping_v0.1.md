# China strategy registry — US mapping (v0.1)

Inventory source: strategy templates and the activation records already in this repo (strategy 8 low-volatility 1.0.3, strategy 9 combined-book v1.3 / `combined_book_v13.py` 1.4.0, strategy 11 momentum-daily). The live `strategies` table was not queried in this pass. A US test or paper activation does not qualify or activate the China row.

`CN-MOM-20D` and `CN-REV-5D` stay at those ids. They are China research candidates. They are not the US momentum books.

| China id | Family | US source | Status |
|---|---|---|---|
| CN-MOM-20D | cn_cross_section | none | CANDIDATE — executable on daily bars |
| CN-REV-5D | cn_cross_section | none | CANDIDATE — executable on daily bars |
| CN-MOM-PORTFOLIO | momentum_portfolio | `templates/momentum_portfolio.py` | BLOCKED — no China point-in-time factor universe |
| CN-MOM-DAILY | momentum_daily | strategy 11, `templates/momentum_daily.py` | BLOCKED — US triggers need US factor state |
| CN-LOWVOL-W | low_volatility | strategy 8, `templates/low_volatility.py` 1.0.3 | BLOCKED — no China 252-day volatility universe |
| CN-SECTOR-W | sector_rotation | `templates/sector_rotation.py` | BLOCKED — no China sector membership |
| CN-COMB-V13 | combined_book | strategy 9, `templates/combined_book_v13.py` 1.4.0 | BLOCKED — US equity sleeve plus a 9-ETF sleeve |
| CN-RANGE-ORB | range | `templates/range_trader.py` | BLOCKED — intraday same-day exit; A-share store is daily bars; T+1 sells. Not RANGE-002 |
| CN-RANGE-VWAP | range_vwap | `templates/range_trader_vwap.py` | BLOCKED — session VWAP and same-day re-entry |

`examples/rsi_meanreversion.py` has no activation record and is not given a China row.

## Parity

| Area | This pass |
|---|---|
| Data | A-share store: bars, calendar, factors, coverage, issues. Shown on `/cn/data`. |
| Strategy list | Persistent `cn_strategies` in the A-share store. `/cn/strategies` reads the China API only. |
| Strategy detail / backtest job | The two candidates still run through the descriptive runner. No progress UI, no parameter form. |
| Results | Existing results page, attached by China id. No equity-curve chart and no benchmark series. |
| Paper account, activation, risk limits | Not built. The China banner stays research-only. |
| Access | US-only, China-only, and both, on routes and APIs (parent branch). |
| MyQuant paper API | Not called. No credential is configured. A custom paper simulator is not started. |
| Real-money China trading | Out of scope. China orders are not wired to Alpaca. |

A laptop file outside git holds one `CN-REV-5D` plumbing run on Tushare daily bars for three main-board names. Two names had no adjustment factor (per-minute limit). The name that had factors produced no fill: before 2026-07-06 the price-limit rule needs an ST flag, and Tushare daily bars do not carry one (`RULE_NOT_CONFIGURED`). The run is labeled plumbing. It is not a performance result, and it is not in git.

Next smallest step: an ST flag, or a disclosed rule for unknown ST, so a real-data run can fill; then the two missing adjustment factors. Paper accounts stay unbuilt until that execution path is real.
