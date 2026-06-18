# Portfolio Construction Study — momentum, v1 (3A)

_Store: factor_data_full.duckdb 2007-01-01..2026-06-12. Methods: equal_weight, inverse_vol, risk_parity_diagonal × {no overlay, vol-target 15%}. risk_parity_diagonal == inverse_vol in v1 (Gotcha 5) — materially a two-method comparison._

## Scorecards (portfolio_backtest gate — frozen §4.7a)

| experiment | verdict | confidence | components |
|---|---|---|---|
| equal_weight/nooverlay | NO-GO | 62 | statistical 4/4 · oos_stability 3/3 · drawdown 0/3 · turnover 1/2 · capacity 0/1 |
| equal_weight/voltgt15 | NO-GO | 62 | statistical 4/4 · oos_stability 3/3 · drawdown 0/3 · turnover 1/2 · capacity 0/1 |
| inverse_vol/nooverlay | NO-GO | 54 | statistical 4/4 · oos_stability 3/3 · drawdown 0/3 · turnover 0/2 · capacity 0/1 |
| inverse_vol/voltgt15 | NO-GO | 54 | statistical 4/4 · oos_stability 3/3 · drawdown 0/3 · turnover 0/2 · capacity 0/1 |
| risk_parity_diagonal/nooverlay | NO-GO | 54 | statistical 4/4 · oos_stability 3/3 · drawdown 0/3 · turnover 0/2 · capacity 0/1 |
| risk_parity_diagonal/voltgt15 | NO-GO | 54 | statistical 4/4 · oos_stability 3/3 · drawdown 0/3 · turnover 0/2 · capacity 0/1 |

## Cross-method metrics

| metric | exp_33a5bc79919e4801 | exp_560564f6fa1cc222 | exp_fcbe11c8bcb8f6d6 | exp_03af73137127977c | exp_dc7cbed96738401b | exp_f860ed89adc45393 | winner |
|---|---|---|---|---|---|---|---|
| sharpe | 0.5391 | 0.5391 | 0.5579 | 0.5579 | 0.5579 | 0.5579 | exp_fcbe11c8bcb8f6d6 |
| sortino | 0.75 | 0.75 | 0.774 | 0.774 | 0.774 | 0.774 | exp_fcbe11c8bcb8f6d6 |
| calmar | 0.1827 | 0.1827 | 0.187 | 0.187 | 0.187 | 0.187 | exp_fcbe11c8bcb8f6d6 |
| max_drawdown | -0.6562 | -0.6562 | -0.6161 | -0.6161 | -0.6161 | -0.6161 | exp_fcbe11c8bcb8f6d6 |
| turnover_annual | 9.479 | 9.479 | 11.69 | 11.69 | 11.69 | 11.69 | exp_33a5bc79919e4801 |

## Per-regime book Sharpe (§4.6 reporting slice)

| regime | equal_weight/nooverlay | equal_weight/voltgt15 | inverse_vol/nooverlay | inverse_vol/voltgt15 | risk_parity_diagonal/nooverlay | risk_parity_diagonal/voltgt15 |
|---|---|---|---|---|---|---|
| bull | 1.48 | 1.48 | 1.49 | 1.49 | 1.49 | 1.49 |
| bear | -1.31 | -1.31 | -1.25 | -1.25 | -1.25 | -1.25 |
| high_vol | 0.326 | 0.326 | 0.324 | 0.324 | 0.324 | 0.324 |
| low_vol | 0.998 | 0.998 | 1.07 | 1.07 | 1.07 | 1.07 |

## Result interpretation — momentum construction study, 2026-06-18, factor_data_full.duckdb 2007-01-01..2026-06-12

- **Best method:**            equal_weight/nooverlay (confidence 62, Sharpe 0.54)
- **Why:**                    highest gate confidence; see the component breakdown above for which dimensions decided it
- **Risk tradeoff:**          maxDD -65.62% vs benchmark -59.94% (excess -5.68%); Sortino 0.75
- **Turnover impact:**        annual turnover 948%, max single-name weight change 0.03
- **Capacity impact:**        avg ADV participation 1132.75%, max rebalance notional $470,963
- **Regime weakness:**        weakest in the **bear** slice
- **Recommended action:**     carry the winner to §3B (capacity model + attribution) — NOT deploy; deployment is owner-gated (ADR 0019)
- **Do NOT do:**              do not enable on the live book on this study alone; the deep-history pool is survivorship-biased (read ΔmaxDD *relatively*, §0 Q6 / Gotcha 6)

