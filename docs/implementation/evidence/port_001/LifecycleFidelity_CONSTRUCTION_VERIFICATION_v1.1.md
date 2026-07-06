# PORT-001 Reproduction — Construction Verification

**Onboarding Gate: PASSED**  ·  Lifecycle Fidelity **96.7%**

| Criterion | Value | Threshold | Pass |
|---|---|---|---|
| sharpe | 0.0091 | 0.05 | ✓ |
| maxdd | 0.0003 | 0.02 | ✓ |
| daily_return_corr | 0.999883 | 0.98 | ✓ |
| weight_corr | 0.999746 | 0.99 | ✓ |
| trade_count | 0.0 | 0.1 | ✓ |
| determinism | 1.0 | 1.0 | ✓ |

- Candidate (Workbench): Sharpe 1.03 · MaxDD -0.0925 · trades 0
- Reference (sibling): Sharpe 1.0209 · MaxDD 0.0922 · trades 0

_Construction-verification: the sibling's OWN sleeve return series blended through the platform PCE/ERC vs its combined book — isolates the construction engine from data-source noise. A clean pass is L1+L2 construction evidence; the self-stack (Alpaca) data-fidelity port is a separate study._
