# RANGE-002 synthetic engineering benchmark - EXPECTATIONS v0.1

Status: WRITTEN BEFORE THE FIRST RUN. NON-INFERENTIAL. Synthetic fixtures only; this proves arithmetic and behaviour of the screen kernel, not any market property. No P0 value is decided here; every spec number is the existing synthetic fixture value (5/15 bps, tick 0.01, OR 09:30-09:59, entry window 10:00-14:59, flat 15:55, half-day offset 4, min OR width 2 ticks, risk 0.1%, or_completeness 0). Added to the synthetic payload only: the seven-candidate `exits.candidates` list and, for S6 only, `risk.per_trade_pct` = 0.25.

Candidates (closed set, kernel family names): TIME (family time); R2, R3 (fixed_r, r_multiple 2.0/3.0); TRAIL1, TRAIL15 (trailing, trail_r 1.0/1.5); SCALE_EOD (scale_out, remainder eod); SCALE_TRAIL (scale_out, remainder trail, trail_r 1.0; the trail value is a harness choice, none was given).

Cost rule: net R = gross R - bps/1e4 x (entry + sum(frac x exit px)) / R_fill, base 5 bps, stress 15 bps per side (stress cost = 3 x base cost). Expected values are computed by arithmetic from the leg prices; test tolerance 1e-6.

## S1 - Trending breakout

All sessions: OR 09:30-09:59 spans 10.00-10.10 (trigger 10.11, R_fill 0.11, 1R 10.22, 2R 10.33, 3R 10.44). Equity 100,000 at 0.1% => $100 risk, qty int(100/0.11)=909.
- AAA 03-02: 10:00-10:04 flat 10.05; 10:05 O10.09 H10.20 L10.08 C10.18 (entry 10.11); 10:06-10:59 flat 10.15; 11:00 O10.15 H10.25 L10.15 C10.24 (+1R); 11:01-11:59 flat 10.24; 12:00 O10.24 H10.36 L10.24 C10.36 (2R target 10.33); 12:01-12:59 flat 10.36; 13:00 O10.36 H10.50 L10.36 C10.50 (3R target 10.44); 13:01-14:29 flat 10.50; 14:30 O10.50 H10.50 L10.30 C10.32; 14:31-15:59 flat 10.32.
  Trail 1.0R stop: after 11:00 close 10.24 -> max(10.00,10.11,10.13)=10.13; after 12:00 close 10.36 -> 10.25; after 13:00 close 10.50 -> 10.39. Trail 1.5R: 11:00 -> max(10.11,10.075)=10.11; 12:00 -> 10.195; 13:00 -> 10.335. 14:30 low 10.30 <= both: fills at the stops 10.39 / 10.335.
- BBB 03-03: OR 10.00-10.10; 10:05 O10.02 H10.03 L9.80 C9.85, then flat 9.85. Downside break only: the kernel is long-only, so NO_BREAKOUT (premise correction: no short side exists in the kernel).
- CCC 03-04: 10:05 break (10.09/10.20/10.08/10.18); 10:06 O10.18 H10.50 L10.18 C10.48 (touches 1R, 2R, 3R in one bar, low above stop); 10:07-15:59 flat 10.48. Trail stop after 10:06: 10.37 (1.0R) / 10.315 (1.5R), never touched.

| symbol | day | expected state | note |
|---|---|---|---|
| AAA | 2026-03-02 | ENTERED | long breakout, staged continuation |
| BBB | 2026-03-03 | NO_BREAKOUT | downside break only; kernel is long-only |
| CCC | 2026-03-04 | ENTERED | long breakout, 3R in one bar then hold |

| symbol | cand | entry | R_fill | legs (frac@px) | exit | reason | qty | gross R | net base | net stress |
|---|---|---|---|---|---|---|---|---|---|---|
| AAA | TIME | 10:05 @10.11 | 0.11 | 1@10.32 | 15:55 | EOD | 909 | 1.909091 | 1.816227 | 1.630500 |
| AAA | R2 | 10:05 @10.11 | 0.11 | 1@10.33 | 12:00 | TARGET | 909 | 2.000000 | 1.907091 | 1.721273 |
| AAA | R3 | 10:05 @10.11 | 0.11 | 1@10.44 | 13:00 | TARGET | 909 | 3.000000 | 2.906591 | 2.719773 |
| AAA | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10.39 | 14:30 | TRAIL_STOP | 909 | 2.545455 | 2.452273 | 2.265909 |
| AAA | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10.335 | 14:30 | TRAIL_STOP | 909 | 2.045455 | 1.952523 | 1.766659 |
| AAA | SCALE_EOD | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.32 | 15:55 | EOD | 909 | 1.454545 | 1.361909 | 1.176636 |
| AAA | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.39 | 14:30 | TRAIL_STOP | 909 | 1.772727 | 1.679932 | 1.494341 |
| CCC | TIME | 10:05 @10.11 | 0.11 | 1@10.48 | 15:55 | EOD | 909 | 3.363636 | 3.270045 | 3.082864 |
| CCC | R2 | 10:05 @10.11 | 0.11 | 1@10.33 | 10:06 | TARGET | 909 | 2.000000 | 1.907091 | 1.721273 |
| CCC | R3 | 10:05 @10.11 | 0.11 | 1@10.44 | 10:06 | TARGET | 909 | 3.000000 | 2.906591 | 2.719773 |
| CCC | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10.48 | 15:55 | EOD | 909 | 3.363636 | 3.270045 | 3.082864 |
| CCC | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10.48 | 15:55 | EOD | 909 | 3.363636 | 3.270045 | 3.082864 |
| CCC | SCALE_EOD | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.48 | 15:55 | EOD | 909 | 2.181818 | 2.088818 | 1.902818 |
| CCC | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.48 | 15:55 | EOD | 909 | 2.181818 | 2.088818 | 1.902818 |

Scenario totals (sum of net R, base / stress): TIME 5.086273 / 4.713364; R2 3.814182 / 3.442545; R3 5.813182 / 5.439545; TRAIL1 5.722318 / 5.348773; TRAIL15 5.222568 / 4.849523; SCALE_EOD 3.450727 / 3.079455; SCALE_TRAIL 3.768750 / 3.397159

Expected funnel: sessions 3; valid sessions (not OR_INCOMPLETE/OR_TOO_NARROW) 3; breakouts (ENTERED + SKIPPED_CROSSED_BEFORE_ARM + ENTRY_AT_OR_AFTER_EOD_CUTOFF) 2; entries 2; terminal states {'ENTERED': 2, 'NO_BREAKOUT': 1}.
Expected exit reasons per candidate: TIME {'EOD': 2}; R2 {'TARGET': 2}; R3 {'TARGET': 2}; TRAIL1 {'TRAIL_STOP': 1, 'EOD': 1}; TRAIL15 {'TRAIL_STOP': 1, 'EOD': 1}; SCALE_EOD {'EOD': 2}; SCALE_TRAIL {'TRAIL_STOP': 1, 'EOD': 1}

## S2 - False breakout and reversal

Same OR/trigger/R/qty as S1.
- DDD 03-05: break at 10:05 (10.09/10.20/10.08/10.18); 10:06 O10.15 H10.16 L9.95 C9.97 (low through stop 10.00, open above it => fills AT the stop); flat 9.97 after.
- EEE 03-06: break 10:05; 10:06-10:29 flat 10.12; 10:30 O10.15 H10.25 L10.15 C10.24 (+1R 10.22 reached); 10:31-11:59 flat 10.20; 12:00 O10.20 H10.20 L9.95 C9.98; flat 9.98 after. After 10:30: trail 1.0R stop 10.13, trail 1.5R stop 10.11 (breakeven floor); scale-out fills half at 10.22; non-trailing candidates still carry stop 10.00.

| symbol | day | expected state | note |
|---|---|---|---|
| DDD | 2026-03-05 | ENTERED | break then reverse through stop |
| EEE | 2026-03-06 | ENTERED | break, +1R, then reverse |

| symbol | cand | entry | R_fill | legs (frac@px) | exit | reason | qty | gross R | net base | net stress |
|---|---|---|---|---|---|---|---|---|---|---|
| DDD | TIME | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| DDD | R2 | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| DDD | R3 | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| DDD | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| DDD | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| DDD | SCALE_EOD | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| DDD | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 1@10 | 10:06 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| EEE | TIME | 10:05 @10.11 | 0.11 | 1@10 | 12:00 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| EEE | R2 | 10:05 @10.11 | 0.11 | 1@10 | 12:00 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| EEE | R3 | 10:05 @10.11 | 0.11 | 1@10 | 12:00 | STOP | 909 | -1.000000 | -1.091409 | -1.274227 |
| EEE | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10.13 | 12:00 | TRAIL_STOP | 909 | 0.181818 | 0.089818 | -0.094182 |
| EEE | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10.11 | 12:00 | TRAIL_STOP | 909 | 0.000000 | -0.091909 | -0.275727 |
| EEE | SCALE_EOD | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10 | 12:00 | STOP | 909 | 0.000000 | -0.091909 | -0.275727 |
| EEE | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.13 | 12:00 | TRAIL_STOP | 909 | 0.590909 | 0.498705 | 0.314295 |

Scenario totals (sum of net R, base / stress): TIME -2.182818 / -2.548455; R2 -2.182818 / -2.548455; R3 -2.182818 / -2.548455; TRAIL1 -1.001591 / -1.368409; TRAIL15 -1.183318 / -1.549955; SCALE_EOD -1.183318 / -1.549955; SCALE_TRAIL -0.592705 / -0.959932

Expected funnel: sessions 2; valid sessions (not OR_INCOMPLETE/OR_TOO_NARROW) 2; breakouts (ENTERED + SKIPPED_CROSSED_BEFORE_ARM + ENTRY_AT_OR_AFTER_EOD_CUTOFF) 2; entries 2; terminal states {'ENTERED': 2}.
Expected exit reasons per candidate: TIME {'STOP': 2}; R2 {'STOP': 2}; R3 {'STOP': 2}; TRAIL1 {'STOP': 1, 'TRAIL_STOP': 1}; TRAIL15 {'STOP': 1, 'TRAIL_STOP': 1}; SCALE_EOD {'STOP': 2}; SCALE_TRAIL {'STOP': 1, 'TRAIL_STOP': 1}

## S3 - Gap entry, gap through stop, costs

OR 10.00-10.10, trigger 10.11, equity 100,000, 0.1%.
- FFF 03-09: 10:00-10:29 flat 10.05; 10:30 O10.20 H10.30 L10.19 C10.28 (open above trigger, not the first entry bar => gap entry at the OPEN 10.20); flat 10.28 after. r_pre 0.11, r_fill 0.20, qty int(100/0.20)=500. 1R=10.40, never reached; all candidates exit at EOD open 10.28.
- GGG 03-10: break 10:05 (entry 10.11); 10:06-10:59 flat 10.15; 11:00 O9.80 H9.85 L9.70 C9.75 (opens below stop 10.00 => fills at the OPEN 9.80, STOP_GAP); flat 9.75 after.
- HHH 03-11: first entry-window bar 10:00 O10.20 H10.25 L10.19 C10.22 (already through trigger at the window start) => SKIPPED_CROSSED_BEFORE_ARM; flat 10.22 after.

| symbol | day | expected state | note |
|---|---|---|---|
| FFF | 2026-03-09 | ENTERED | gap entry at 10:30 open 10.20 |
| GGG | 2026-03-10 | ENTERED | gap through the stop at 11:00 |
| HHH | 2026-03-11 | SKIPPED_CROSSED_BEFORE_ARM | gap open on first bar |

| symbol | cand | entry | R_fill | legs (frac@px) | exit | reason | qty | gross R | net base | net stress |
|---|---|---|---|---|---|---|---|---|---|---|
| FFF | TIME | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| FFF | R2 | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| FFF | R3 | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| FFF | TRAIL1 | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| FFF | TRAIL15 | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| FFF | SCALE_EOD | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| FFF | SCALE_TRAIL | 10:30 @10.2 | 0.2 | 1@10.28 | 15:55 | EOD gap | 500 | 0.400000 | 0.348800 | 0.246400 |
| GGG | TIME | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |
| GGG | R2 | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |
| GGG | R3 | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |
| GGG | TRAIL1 | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |
| GGG | TRAIL15 | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |
| GGG | SCALE_EOD | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |
| GGG | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 1@9.8 | 11:00 | STOP_GAP | 909 | -2.818182 | -2.908682 | -3.089682 |

Scenario totals (sum of net R, base / stress): TIME -2.559882 / -2.843282; R2 -2.559882 / -2.843282; R3 -2.559882 / -2.843282; TRAIL1 -2.559882 / -2.843282; TRAIL15 -2.559882 / -2.843282; SCALE_EOD -2.559882 / -2.843282; SCALE_TRAIL -2.559882 / -2.843282

Expected funnel: sessions 3; valid sessions (not OR_INCOMPLETE/OR_TOO_NARROW) 3; breakouts (ENTERED + SKIPPED_CROSSED_BEFORE_ARM + ENTRY_AT_OR_AFTER_EOD_CUTOFF) 3; entries 2; terminal states {'ENTERED': 2, 'SKIPPED_CROSSED_BEFORE_ARM': 1}.
Expected exit reasons per candidate: TIME {'EOD': 1, 'STOP_GAP': 1}; R2 {'EOD': 1, 'STOP_GAP': 1}; R3 {'EOD': 1, 'STOP_GAP': 1}; TRAIL1 {'EOD': 1, 'STOP_GAP': 1}; TRAIL15 {'EOD': 1, 'STOP_GAP': 1}; SCALE_EOD {'EOD': 1, 'STOP_GAP': 1}; SCALE_TRAIL {'EOD': 1, 'STOP_GAP': 1}

## S4 - Missing data and unavailable exits

OR 10.00-10.10, trigger 10.11, R 0.11; or_max_gap_minutes 0 (the fixtures' synth_payload value).
- III 03-12: no bar and DATA_GAP at 09:40 => OR_INCOMPLETE (day invalid, counted in the funnel). The rest of the day would have broken out.
- JJJ 03-13: break 10:05; flat 10.30 from 10:06; minute 10:20 has no bar and is DATA_GAP (outside the OR, so the day stays valid). No exit decision falls on the first bar after the gap. 1R 10.22 is reached (trailing armed, scale-out half at 10.22), 2R 10.33 never; stops never touched.
- KKK 03-16: break 10:05; flat 10.30 10:06-14:00; no bars and halted 14:01-15:59 => no executable exit; valued at worse of last close 10.30 and initial stop 10.00 = 10.00, reason EOD_LASTBAR_FALLBACK, exit_unexecutable, exit time 14:00 (last bar). Scale-out candidates still book the 10.22 half at 10:06.
- LLL 03-17: DATA_GAP at 09:40 and 09:41 (2 > allowed 0) => OR_INCOMPLETE.
- MMM 03-18: break 10:05; flat 10.15 10:06-10:59; halted 11:00-11:29; 11:30 O9.70 H9.75 L9.65 C9.72 (first bar after the halt, opens below stop) => fills at the open 9.70, STOP_GAP, exit_after_unavailable, not unexecutable.

| symbol | day | expected state | note |
|---|---|---|---|
| III | 2026-03-12 | OR_INCOMPLETE | 1 DATA_GAP minute in OR |
| JJJ | 2026-03-13 | ENTERED | DATA_GAP 10:20 outside OR |
| KKK | 2026-03-16 | ENTERED | halted 14:01 to close: unexecutable |
| LLL | 2026-03-17 | OR_INCOMPLETE | 2 DATA_GAP minutes in OR |
| MMM | 2026-03-18 | ENTERED | halt 11:00-11:29, reopen below stop |

| symbol | cand | entry | R_fill | legs (frac@px) | exit | reason | qty | gross R | net base | net stress |
|---|---|---|---|---|---|---|---|---|---|---|
| JJJ | TIME | 10:05 @10.11 | 0.11 | 1@10.3 | 15:55 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| JJJ | R2 | 10:05 @10.11 | 0.11 | 1@10.3 | 15:55 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| JJJ | R3 | 10:05 @10.11 | 0.11 | 1@10.3 | 15:55 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| JJJ | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10.3 | 15:55 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| JJJ | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10.3 | 15:55 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| JJJ | SCALE_EOD | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.3 | 15:55 | EOD | 909 | 1.363636 | 1.271045 | 1.085864 |
| JJJ | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.3 | 15:55 | EOD | 909 | 1.363636 | 1.271045 | 1.085864 |
| KKK | TIME | 10:05 @10.11 | 0.11 | 1@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | -1.000000 | -1.091409 | -1.274227 |
| KKK | R2 | 10:05 @10.11 | 0.11 | 1@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | -1.000000 | -1.091409 | -1.274227 |
| KKK | R3 | 10:05 @10.11 | 0.11 | 1@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | -1.000000 | -1.091409 | -1.274227 |
| KKK | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | -1.000000 | -1.091409 | -1.274227 |
| KKK | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | -1.000000 | -1.091409 | -1.274227 |
| KKK | SCALE_EOD | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | 0.000000 | -0.091909 | -0.275727 |
| KKK | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10 | 14:00 | EOD_LASTBAR_FALLBACK UNEXEC after-unavail | 909 | 0.000000 | -0.091909 | -0.275727 |
| MMM | TIME | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |
| MMM | R2 | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |
| MMM | R3 | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |
| MMM | TRAIL1 | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |
| MMM | TRAIL15 | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |
| MMM | SCALE_EOD | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |
| MMM | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 1@9.7 | 11:30 | STOP_GAP after-unavail | 909 | -3.727273 | -3.817318 | -3.997409 |

Scenario totals (sum of net R, base / stress): TIME -3.274227 / -3.822682; R2 -3.274227 / -3.822682; R3 -3.274227 / -3.822682; TRAIL1 -3.274227 / -3.822682; TRAIL15 -3.274227 / -3.822682; SCALE_EOD -2.638182 / -3.187273; SCALE_TRAIL -2.638182 / -3.187273

Expected funnel: sessions 5; valid sessions (not OR_INCOMPLETE/OR_TOO_NARROW) 3; breakouts (ENTERED + SKIPPED_CROSSED_BEFORE_ARM + ENTRY_AT_OR_AFTER_EOD_CUTOFF) 3; entries 3; terminal states {'OR_INCOMPLETE': 2, 'ENTERED': 3}.
Expected exit reasons per candidate: TIME {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}; R2 {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}; R3 {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}; TRAIL1 {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}; TRAIL15 {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}; SCALE_EOD {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}; SCALE_TRAIL {'EOD': 1, 'EOD_LASTBAR_FALLBACK': 1, 'STOP_GAP': 1}

## S5 - Half-day cutoff

Session close 13:00 => flat time 13:00 - 4 min = 12:56; OR/trigger/R as S1. Bars end 12:59. (Dates are synthetic labels; the kernel takes the close time from the session, not a calendar.)
- NNN 03-19: break 10:05, flat 10.30 10:06-12:59 => exits at 12:56 open 10.30 (1R reached, 2R not).
- OOO 03-20: flat 10.05 10:00-12:54; 12:55 O10.09 H10.20 L10.08 C10.18 (last minute before cutoff, entered at 10.11); 12:56-12:59 flat 10.18 => exit at the 12:56 open 10.18.
- QQQ 03-23: flat 10.05 until 12:55; 12:56 O10.09 H10.20 L10.08 C10.18 (breakout bar starts AT the cutoff) => ENTRY_AT_OR_AFTER_EOD_CUTOFF, no trade.

| symbol | day | expected state | note |
|---|---|---|---|
| NNN | 2026-03-19 | ENTERED | half day, break 10:05, flat 12:56 |
| OOO | 2026-03-20 | ENTERED | half day, break 12:55, flat 12:56 |
| QQQ | 2026-03-23 | ENTRY_AT_OR_AFTER_EOD_CUTOFF | half day, break 12:56 = cutoff |

| symbol | cand | entry | R_fill | legs (frac@px) | exit | reason | qty | gross R | net base | net stress |
|---|---|---|---|---|---|---|---|---|---|---|
| NNN | TIME | 10:05 @10.11 | 0.11 | 1@10.3 | 12:56 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| NNN | R2 | 10:05 @10.11 | 0.11 | 1@10.3 | 12:56 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| NNN | R3 | 10:05 @10.11 | 0.11 | 1@10.3 | 12:56 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| NNN | TRAIL1 | 10:05 @10.11 | 0.11 | 1@10.3 | 12:56 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| NNN | TRAIL15 | 10:05 @10.11 | 0.11 | 1@10.3 | 12:56 | EOD | 909 | 1.727273 | 1.634500 | 1.448955 |
| NNN | SCALE_EOD | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.3 | 12:56 | EOD | 909 | 1.363636 | 1.271045 | 1.085864 |
| NNN | SCALE_TRAIL | 10:05 @10.11 | 0.11 | 0.5@10.22 + 0.5@10.3 | 12:56 | EOD | 909 | 1.363636 | 1.271045 | 1.085864 |
| OOO | TIME | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |
| OOO | R2 | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |
| OOO | R3 | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |
| OOO | TRAIL1 | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |
| OOO | TRAIL15 | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |
| OOO | SCALE_EOD | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |
| OOO | SCALE_TRAIL | 12:55 @10.11 | 0.11 | 1@10.18 | 12:56 | EOD | 909 | 0.636364 | 0.544136 | 0.359682 |

Scenario totals (sum of net R, base / stress): TIME 2.178636 / 1.808636; R2 2.178636 / 1.808636; R3 2.178636 / 1.808636; TRAIL1 2.178636 / 1.808636; TRAIL15 2.178636 / 1.808636; SCALE_EOD 1.815182 / 1.445545; SCALE_TRAIL 1.815182 / 1.445545

Expected funnel: sessions 3; valid sessions (not OR_INCOMPLETE/OR_TOO_NARROW) 3; breakouts (ENTERED + SKIPPED_CROSSED_BEFORE_ARM + ENTRY_AT_OR_AFTER_EOD_CUTOFF) 3; entries 2; terminal states {'ENTERED': 2, 'ENTRY_AT_OR_AFTER_EOD_CUTOFF': 1}.
Expected exit reasons per candidate: TIME {'EOD': 2}; R2 {'EOD': 2}; R3 {'EOD': 2}; TRAIL1 {'EOD': 2}; TRAIL15 {'EOD': 2}; SCALE_EOD {'EOD': 2}; SCALE_TRAIL {'EOD': 2}

## S6 - Competing signals, constrained capital

OR 10.00-10.15 (width 0.15 = 15 ticks), trigger 10.16, R_fill 0.16, 1R 10.32. Synthetic payload overrides risk.per_trade_pct = 0.25 (percent), the only changed value; equity 20,000 => $50 risk, qty int(50/0.16)=312, notional 312 x 10.16 = 3,169.92 = 15.85% of equity. Limits from the payload via limits_from_draft: max_concurrent 2, gross_cap 0.3 (6,000), per_name_cap 0.2 (4,000), daily_loss_limit 0.4 R, tie-break PERMATICKER_ASC.
Break bar 10.10/10.17/10.09/10.15 at the stated minute; winners flat 10.20 to the close (never touch 1R/stop) => EOD 15:55 at 10.20 for ALL seven candidates; losers flat 10.12 until the exit minute, then O10.12 H10.12 L9.95 C9.97 => STOP at 10.00 for ALL seven candidates.
- Day 03-30: SYM1..SYM5 all break at 10:05 with permatickers PM-E, PM-D, PM-C, PM-B, PM-A (symbol order is the reverse of permaticker order).
- Day 03-31: LOS1 (PM-L) breaks 10:05, stopped 10:15; WIN1 (PM-A) breaks 10:10; WIN2 (PM-B) breaks 10:20.
- Day 04-01: LOS2 (PM-A) breaks 10:05, stopped 10:20; WIN3 (PM-B) breaks 10:20 (same minute as LOS2's exit).

| symbol | day | expected state | note |
|---|---|---|---|
| SYM1 | 2026-03-30 | ENTERED | perm PM-E, 10:05 winner |
| SYM2 | 2026-03-30 | ENTERED | perm PM-D, 10:05 winner |
| SYM3 | 2026-03-30 | ENTERED | perm PM-C, 10:05 winner |
| SYM4 | 2026-03-30 | ENTERED | perm PM-B, 10:05 winner |
| SYM5 | 2026-03-30 | ENTERED | perm PM-A, 10:05 winner |
| LOS1 | 2026-03-31 | ENTERED | perm PM-L, 10:05 loser exits 10:15 |
| WIN1 | 2026-03-31 | ENTERED | perm PM-A, 10:10 winner |
| WIN2 | 2026-03-31 | ENTERED | perm PM-B, 10:20 winner |
| LOS2 | 2026-04-01 | ENTERED | perm PM-A, 10:05 loser exits 10:20 |
| WIN3 | 2026-04-01 | ENTERED | perm PM-B, 10:20 winner |

| symbol | cand | entry | R_fill | legs (frac@px) | exit | reason | qty | gross R | net base | net stress |
|---|---|---|---|---|---|---|---|---|---|---|
| SYM1 | TIME | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM1 | R2 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM1 | R3 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM1 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM1 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM1 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM1 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | TIME | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | R2 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | R3 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM2 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | TIME | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | R2 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | R3 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM3 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | TIME | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | R2 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | R3 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM4 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | TIME | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | R2 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | R3 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| SYM5 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| LOS1 | TIME | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS1 | R2 | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS1 | R3 | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS1 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS1 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS1 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS1 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10 | 10:15 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| WIN1 | TIME | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN1 | R2 | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN1 | R3 | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN1 | TRAIL1 | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN1 | TRAIL15 | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN1 | SCALE_EOD | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN1 | SCALE_TRAIL | 10:10 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | TIME | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | R2 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | R3 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | TRAIL1 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | TRAIL15 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | SCALE_EOD | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN2 | SCALE_TRAIL | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| LOS2 | TIME | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS2 | R2 | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS2 | R3 | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS2 | TRAIL1 | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS2 | TRAIL15 | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS2 | SCALE_EOD | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| LOS2 | SCALE_TRAIL | 10:05 @10.16 | 0.16 | 1@10 | 10:20 | STOP | 312 | -1.000000 | -1.063000 | -1.189000 |
| WIN3 | TIME | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN3 | R2 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN3 | R3 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN3 | TRAIL1 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN3 | TRAIL15 | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN3 | SCALE_EOD | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |
| WIN3 | SCALE_TRAIL | 10:20 @10.16 | 0.16 | 1@10.2 | 15:55 | EOD | 312 | 0.250000 | 0.186375 | 0.059125 |

Scenario totals (sum of net R, base / stress): TIME -0.635000 / -1.905000; R2 -0.635000 / -1.905000; R3 -0.635000 / -1.905000; TRAIL1 -0.635000 / -1.905000; TRAIL15 -0.635000 / -1.905000; SCALE_EOD -0.635000 / -1.905000; SCALE_TRAIL -0.635000 / -1.905000

Expected funnel: sessions 10; valid sessions (not OR_INCOMPLETE/OR_TOO_NARROW) 10; breakouts (ENTERED + SKIPPED_CROSSED_BEFORE_ARM + ENTRY_AT_OR_AFTER_EOD_CUTOFF) 10; entries 10; terminal states {'ENTERED': 10}.
Expected exit reasons per candidate: TIME {'EOD': 8, 'STOP': 2}; R2 {'EOD': 8, 'STOP': 2}; R3 {'EOD': 8, 'STOP': 2}; TRAIL1 {'EOD': 8, 'STOP': 2}; TRAIL15 {'EOD': 8, 'STOP': 2}; SCALE_EOD {'EOD': 8, 'STOP': 2}; SCALE_TRAIL {'EOD': 8, 'STOP': 2}

### S6 portfolio-constrained expectations (identical for all seven candidates)

Signal level: 10 trades, 8 winners (net base 0.186375, stress 0.059125) and 2 losers (base -1.063, stress -1.189): total base -0.635000, mean -0.063500, profit factor 1.491/2.126 = 0.701317, win rate 0.8, max daily drawdown 1.566875 R (day sums 0.931875, -0.69025, -0.876625), net after removing top 5 = -1.566875, best-day share undefined (total < 0).

Default limits (gross cap 0.3 binds): 03-30 PM-A (SYM5) accepted first by the permaticker tie-break, SYM4/SYM3/SYM2/SYM1 rejected GROSS_CAP (2 x 3,169.92 > 6,000); 03-31 LOS1 accepted, WIN1 rejected GROSS_CAP (LOS1 still open at 10:10), WIN2 rejected DAILY_LOSS_LIMIT (realised -1.063 <= -0.4 after LOS1's 10:15 exit); 04-01 LOS2 accepted, WIN3 rejected GROSS_CAP (LOS2 exits at 10:20, NOT released in the same minute, and no realised R yet). Accepted 3 (SYM5, LOS1, LOS2), rejected {GROSS_CAP 6, DAILY_LOSS_LIMIT 1}; portfolio net base 0.186375 - 2.126 = -1.939625, stress -2.318875.

Concurrency variant (harness relaxes gross_cap to 1.0; NOT a spec value): 03-30 SYM5, SYM4 accepted (PM-A, PM-B), SYM3/SYM2/SYM1 rejected MAX_CONCURRENT; 03-31 LOS1, WIN1 accepted, WIN2 DAILY_LOSS_LIMIT; 04-01 LOS2, WIN3 accepted (open count 1 at 10:20). Accepted 6, rejected {MAX_CONCURRENT 3, DAILY_LOSS_LIMIT 1}; net base 4 x 0.186375 - 2.126 = -1.380500, stress 0.2365 - 2.378 = -2.141500.

## Pooled bootstrap and selection stage (optional, harness-level)

All S1-S6 trades pooled per candidate, eligible days = every distinct session day (day-cluster stationary bootstrap, mean block 2.5, reps 13, seed 14 = the synthetic payload `stats.bootstrap` values; confidence 0.9, alpha 0.07 likewise). Expected: build_day_matrix observed mean net R equals the pooled mean below; same seed gives identical output twice. Selection uses payload `exits.selection` (min_trades 7, min_pf 1.5, tie 0.5) with score = mean base net R and complexity order TIME, R2, R3, TRAIL1, TRAIL15, SCALE_EOD, SCALE_TRAIL (harness mapping of the family order; the spec's complexity_order lists families, not candidate ids).

| cand | pooled trades | pooled mean net base | profit factor |
|---|---|---|---|
| TIME | 21 | -0.066048 | 0.885618 |
| R2 | 21 | -0.126624 | 0.780714 |
| R3 | 21 | -0.031434 | 0.945564 |
| TRAIL1 | 21 | 0.020488 | 1.038991 |
| TRAIL15 | 21 | -0.011963 | 0.977422 |
| SCALE_EOD | 21 | -0.083356 | 0.827152 |
| SCALE_TRAIL | 21 | -0.040087 | 0.916113 |

Expected selection result: all seven candidates have 21 trades (>= 7) but pooled profit factor <= 1.5 (max 1.04), so winner None, reason NO_ELIGIBLE_CANDIDATE, every candidate PF_BELOW_FLOOR. Expected max-statistic test: observed_argmax TRAIL1 (highest pooled mean), observed_max 0.020488; its p-value and the intervals are asserted only for determinism.

Criteria stage (`classify_family`) is NOT run: it needs threshold values that are not in the synthetic payload and none is invented here.
