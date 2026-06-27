# Runbook — High backend CPU / asyncio event-loop spin

**When to use:** the `workbench-backend` container shows sustained high CPU (one core pinned at
~100%) while it should be mostly idle — most visible in Docker Desktop's Containers view as a single
row at ~100% while everything else is near 0. This runbook is the **how-to-diagnose** procedure
(generic, py-spy based) plus the **2026-06-27 incident** as a fully worked example.

> TL;DR of the worked example: alpaca-py's `StockDataStream._run_forever()` **busy-waits on
> `await asyncio.sleep(0)`** when the bar stream is connected with **no symbols subscribed** →
> one core pinned at 100%. Fixed by driving the connection ourselves (`_start_ws` → `_consume`)
> instead of `_run_forever`. Backend CPU **~100% → ~1.2%**. (commit `4396e2a`, PR #295.)

### Incident classification (2026-06-27)

| Field | Value |
|---|---|
| **Incident type** | Operational (performance) |
| **Component** | Market-data streaming (`bar_stream_adapter_alpaca`) |
| **Severity** | Medium |
| **Customer impact** | None (paper books; fills unaffected) |
| **Performance impact** | High (one core pinned ~100%, socket churn) |
| **Detection** | Manual (Docker Desktop CPU view) |

### Decision summary (read this if you read nothing else)

```
Problem          one backend core pinned at ~100%
   ↓
Symptom          asyncio event-loop spin (main thread, not a worker)
   ↓
Cause            alpaca-py StockDataStream._run_forever() busy-waits on
                 `await asyncio.sleep(0)` while no symbols are subscribed
   ↓
Decision         own the connection lifecycle — DON'T call _run_forever();
                 drive _start_ws → _consume, let our supervisor own reconnect
   ↓
Result           CPU ~100% → ~1.2%   ·   sockets-to-Alpaca 17 → 9
```

### Architecture of the change (old vs new)

```
OLD (busy-spin)                          NEW (supervised)
─────────────────                        ──────────────────
BarStreamService._run                    BarStreamService._run   ← owns reconnect + CAPPED backoff
   └─ adapter.connect()                     └─ adapter.connect()
        └─ stream._run_forever()  ✗              └─ _connect_and_consume()  ✓
             while not subscribed:                    └─ stream._start_ws()   (one connect)
               await asyncio.sleep(0) ← SPIN          └─ stream._consume()    (until drop → raises)
             (+ reconnect: sleep(0.01))           task ENDS on disconnect → outer loop retries
```

---

## 0. The golden rule

**Do NOT diagnose CPU from logs.** A log that is *spamming* is not necessarily the thing burning
CPU — and the real spinner is often **silent**. In the worked example below, a noisy
"trading stream websocket error, restarting" log sent the first fix at the wrong subsystem; CPU
stayed at 100%. **Only a profiler (py-spy) tells you the truth.** Trust the stack sample, not the
correlation.

---

## 1. Confirm it's the backend and it's sustained

```bash
docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -i backend
```
`100%` on a host with 20 logical CPUs = **one core fully used** (Docker reports `100% / 2000%`), i.e.
~5% of the machine. Annoying and wasteful (and it leaks sockets / wastes power), but rarely a hard
outage. Sample twice a few seconds apart to confirm it's *sustained*, not a momentary scheduled job.

## 2. Find the hot thread (is it the asyncio loop, or a worker?)

`ps` is not in the slim image, so read `/proc` directly. The container's PID 1 is the entrypoint
`sh`; the real process is the `uvicorn`/`python` child:

```bash
docker compose exec -T backend sh -c '
  PID=""
  for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); case "$c" in *python*|*uvicorn*) PID=$(basename $p); break;; esac; done
  echo "python pid=$PID"
  # per-thread total ticks (utime+stime); the busiest is the hot thread
  for t in /proc/$PID/task/*; do s=$(cat $t/stat 2>/dev/null); echo "$(basename $t) $(echo $s|awk "{print \$14+\$15}") $(cat $t/comm)"; done | sort -k2 -rn | head -6
  # 1s delta of the busiest thread (100 ticks/s = one full core)
  TID=$(for t in /proc/$PID/task/*; do s=$(cat $t/stat 2>/dev/null); echo "$(basename $t) $(echo $s|awk "{print \$14+\$15}")"; done | sort -k2 -rn | head -1 | awk "{print \$1}")
  a=$(cat /proc/$PID/task/$TID/stat|awk "{print \$14+\$15}"); sleep 1; b=$(cat /proc/$PID/task/$TID/stat|awk "{print \$14+\$15}")
  echo "busiest tid=$TID delta=$((b-a)) ticks/s"
'
```
If the **main thread** (the one matching the uvicorn PID) is at ~100 ticks/s and worker threads are
idle → it's the **asyncio event loop**. (If a *worker* thread is hot instead, suspect a thread-pool
task — pandas, crypto/Fernet key derivation, a sync library call — not a coroutine.)

## 3. Get the real Python stack with py-spy (the decisive step)

The container has no `SYS_PTRACE` capability, so py-spy can't attach in-place. Use a **privileged
sidecar** that shares the backend's PID namespace — non-invasive, no `docker-compose.yml` edit:

```bash
# 1. snapshot the running container into a temp image (so py-spy is available even if you pip-installed it live)
docker compose exec -T backend pip install -q py-spy      # one-time; or bake it
docker commit workbench-backend tmp-backend-pyspy

# 2. find the uvicorn PID (usually 11) as in §2, then RECORD for a few seconds.
#    Use `record`, NOT `dump`: a single `dump` of a fast-churning spin often shows only the bare
#    event loop. `record --format raw` aggregates folded stacks so the hot frame stands out.
docker run --rm --pid=container:workbench-backend --cap-add SYS_PTRACE --network none tmp-backend-pyspy \
  sh -c 'py-spy record --pid 11 --duration 5 --rate 200 --format raw -o /tmp/p.txt >/dev/null 2>&1;
         awk "{c=\$NF; \$NF=\"\"; print c\"\t\"\$0}" /tmp/p.txt | sort -rn | head -12'

# 3. cleanup
docker rmi tmp-backend-pyspy
```
Read the output: the **highest-count folded stacks** (after the unavoidable bare-loop frame) point
straight at the spinning function and file:line. That is your culprit — no guessing.

## 4. Verify the fix worked

After patching + `docker compose build backend && docker compose up -d backend`:
```bash
docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}" | grep -i backend   # expect low single digits
# established sockets from the python proc (a churning reconnect leaks these — expect it to settle):
docker compose exec -T backend sh -c 'P=$(for p in /proc/[0-9]*; do case "$(cat $p/comm 2>/dev/null)" in *python*|*uvicorn*) echo $(basename $p); break;; esac; done); echo "established: $(grep -c " 01 " /proc/$P/net/tcp 2>/dev/null)"'
# services still healthy:
docker compose logs backend | grep -E "alpaca_bar_stream_connected|trade_updates_stream_started|range_autoselect_scheduled" | tail
```

---

## 5. The 2026-06-27 incident (worked example)

### What was the issue
`workbench-backend` was pinned at **~100% of one core** continuously, idle otherwise. Flagged from
the Docker Desktop Containers view (one row at ~100%, the rest ~0).

### How it was diagnosed
- §2 showed the **main asyncio thread** (uvicorn tid 11) accruing ~101 ticks/s; all worker threads
  idle → an **event-loop spin**, not a worker/pandas/crypto task.
- **First wrong turn (the golden-rule lesson):** the logs were spamming
  `trading stream websocket error, restarting — connection: no close frame received or sent` from
  the Alpaca **trade-updates** stream. That looked like the cause; it wasn't. Fixing the
  trade-updates stream removed the *spam* but **CPU stayed at 100%**.
- **§3 py-spy `record`** gave the truth: every hot folded stack was in
  **`alpaca/data/live/websocket.py` `_run_forever`** — the **`StockDataStream`** (bar/market-data
  stream), line ~331.

### Root cause
alpaca-py's `StockDataStream._run_forever()` has a **pre-subscription wait-loop** that runs *until
something is subscribed*:
```python
while not self._subscriptions:      # nothing subscribed yet
    if not self._stop_stream_queue.empty(): ...
    await asyncio.sleep(0)          # <-- yields then IMMEDIATELY reschedules => 100% CPU
```
Our bar stream connects on boot and is frequently up with **no symbols subscribed** (no live
strategy is streaming bars at that moment), so the loop spins on `asyncio.sleep(0)` forever.

> **Why `asyncio.sleep(0)` is dangerous.** `asyncio.sleep(0)` is a **cooperative yield, not a delay**:
> it hands control back to the event loop and then *immediately* reschedules the coroutine on the very
> next iteration. Inside a tight polling loop (`while <cond>: await asyncio.sleep(0)`) it therefore
> consumes an **entire CPU core** while making no progress — it looks like "yielding politely" but is a
> 100%-CPU busy-wait. Use `asyncio.sleep(0)` only to yield *once*; never as the only await in a loop.
> A real poll needs a real delay (`asyncio.sleep(0.1)`+) or, better, an event to await.

(alpaca-py's *trade-updates* `TradingStream` uses `sleep(0.1)` in the same spot, which is why that one
didn't spin — only the **data** stream uses `sleep(0)`.) **This was not a Norton/network problem at
all** — it spins even when the socket is perfectly healthy, simply because nothing is subscribed.

Secondary (same family): both alpaca `_run_forever` variants reconnect with only
`await asyncio.sleep(0.01)` between attempts, so a **Norton-MITM-torn socket** also spins and leaks
sockets (we saw 17 established connections to Alpaca).

### How it was fixed
Stop calling alpaca-py's `_run_forever` (its internal wait/reconnect loop is the bug and we can't
change its sleeps). Drive the connection ourselves with the SDK's own primitives:

- **`app/services/bar_stream_adapter_alpaca.py`** — the task now runs **one connection lifecycle**:
  `await self._stream._start_ws()` (connect + auth + (re)subscribe) → `await self._stream._consume()`
  (receive until the socket drops, which *raises*, or stop is signalled, which *returns*). There is
  **no internal wait/reconnect loop**, so the busy-wait is gone. The **outer**
  `BarStreamService._run` already supervises reconnect with **capped** exponential backoff, so a
  disconnect just ends the task and the outer loop retries cleanly.
- **`app/brokers/alpaca/streaming.py`** (trade-updates) — kept as good defensive code: a supervised
  loop with real exponential backoff + **auto-disable after K rapid failures** (`_MAX_CONSECUTIVE_FAILURES`).
  When disabled, **fills are still captured by the `account_sync` / `position_sync` reconciliation
  polling jobs** (which run every few seconds), so nothing is lost.

> **Why this is the right shape:** the SDK's `_run_forever` couples "wait for subscription",
> "consume", and "reconnect" into one loop with hardcoded sleeps. We only want **one connection
> lifecycle** per call and let *our* supervisor own reconnect/backoff. Driving `_start_ws`/`_consume`
> directly gives exactly that and bypasses both bad sleeps. (Depends on alpaca-py internals — pinned
> version; re-check `_start_ws` / `_consume` / `close` on any alpaca-py upgrade.)

### Result

| Metric | Before | After |
|---|---|---|
| Backend CPU (one core) | **~100%** | **~1.2%** (sustained) |
| Established sockets to Alpaca | **17** (churning) | **9** (stable) |
| Bar / trade-updates / scheduler | healthy | healthy |
| Tests · ruff · mypy | — | green |

Tests: `tests/brokers/alpaca/test_streaming.py`, `tests/services/test_bar_stream.py`.

---

## 6. Generalizable lessons (for the next high-CPU event)

1. **Profile, don't correlate.** A spamming log ≠ the CPU hog. Always confirm with py-spy `record`.
2. **`dump` vs `record`.** A single `py-spy dump` of a fast spin frequently shows only
   `asyncio/runners.py … run()` (the bare loop) — that *itself* is a signal (selector/callback
   churn, no deep Python frame). Use `record` over a few seconds to see the recurring frame.
3. **`SYS_PTRACE` sidecar** is the way to profile our slim, unprivileged container without editing
   compose (§3).
4. **The `_run_forever` anti-pattern.** Any third-party "run forever" coroutine that hides its own
   `while True` + `asyncio.sleep(small)` reconnect/wait loop will defeat *our* outer supervision and
   can busy-spin. Prefer driving the library's per-connection primitives and owning the
   reconnect/backoff ourselves. Grep for risk: `grep -rn "_run_forever\|sleep(0)\b" apps/backend/app`.
5. **A pinned core is cheap-but-real.** It rarely takes the app down (1 of 20 cores) but it leaks
   resources (sockets), wastes power, and masks other load — fix it, don't normalize it.

> **Adoption principle (transferable beyond Alpaca):** *Any third-party SDK that embeds its own
> reconnect / "run forever" loop must be evaluated before adoption — check how it backs off and
> whether it can busy-spin. TradingWorkbench owns connection supervision (connect → consume →
> reconnect/backoff) whenever practical, and treats a vendor's `run_forever()` as a primitive to be
> driven, not a loop to be trusted.*

## 7. This runbook is Evidence Engineering, applied to operations

The same discipline the platform uses for trading research produced this fix — the loop is identical,
just pointed at a process instead of a strategy:

```
Observation (CPU 100%) → Hypothesis (which subsystem?) → Measurement (py-spy record)
   → Root cause (sleep(0) busy-wait) → Fix (own the lifecycle) → Verification (CPU ~1.2%, re-measured)
```

The first hypothesis (trade-updates stream) was **rejected by measurement**, not by argument — exactly
as a research verdict is. Operations gets the same "evidence precedes the decision" treatment as
investment research: this is Evidence Engineering for software operations, not just for trading.

## Related

- **Code:** `app/services/bar_stream_adapter_alpaca.py` (the fix), `app/services/bar_stream.py`
  (`BarStreamService._run`, the outer reconnect supervisor), `app/brokers/alpaca/streaming.py`
  (trade-updates supervised loop). Commit `4396e2a`; PR #295.
- **Doc separation:** this is a **runbook** — *what an operator does* to diagnose/fix. The *why* of
  "TradingWorkbench owns streaming supervision" is architecture: if that principle is reused for a
  second SDK, capture it as an **ADR** ("streaming supervision / external-SDK connection ownership")
  and link it here. None exists yet — it becomes worth writing on the second occurrence.

_Last updated: 2026-06-27 (incident + fix + owner doc-review fold, 9.9/10; commit `4396e2a`, PR #295)._
