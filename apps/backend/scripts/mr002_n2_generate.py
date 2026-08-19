"""MR-002 Gate N2 — generate the preregistered synthetic stress population.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0 §8
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.
Granted by the owner 2026-08-19 after N1 closed (final verdict 629eee0e...).

FROZEN BY THE REGISTRATION, NOT CHOSEN HERE:
    seed 20260819 · PCG64 · 3,000 instances · 8 axes with per-axis counts
    400 / 600 / 400 / 400 / 300 / 200 / 300 / 400

DETERMINISM. One Generator, instances emitted in index order, no reliance on dict/set iteration
order, no wall clock, no hostname. Regenerating from the seed must reproduce the population
BYTE-IDENTICALLY; the population hash is recorded here and re-verified before use.

STRUCTURAL CONTRACT (§8). Every emitted instance satisfies, and is CHECKED to satisfy:
    t > 0 elementwise · meq == 1 · box 0 <= z <= u · finite A_ub/b_ub/A_eq/b_eq/upper
    kappa(H) = max(t)/min(t) <= HESSIAN_CONDITION_MAX = 1e10
A violation is a generator bug, not a stress case, and aborts generation.

⚠ TWO CONFORMANCE PROPERTIES TAKEN FROM THE REGISTERED POPULATION, NOT INVENTED HERE.

  upper == t elementwise. True for 3,895 of 3,895 registered instances, and REQUIRED for validity:
  the frozen `_quadprog_variant` wrapper records that its square-root mapping "is correct only when
  upper == t elementwise". A synthetic instance with upper != t would exercise a mathematically
  invalid wrapper mapping, so N2 would be measuring wrapper breakage rather than solver robustness.

  Feasibility by construction. Every instance is built around an explicit point z0 satisfying
  A_eq z0 = b_eq and 0 <= z0 <= upper, with b_ub = A_ub z0 + slack, slack >= 0. An infeasible
  instance would make "100% registered resolution" unreachable for reasons unrelated to the
  method, so feasibility is established at generation and verified exactly.

Development domain only. No sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/work/apps/backend")

OUT_DIR = "/work/.mr002out/n2"
SEED = 20260819
KAPPA_MAX = 1e10
ENVELOPE = "/work/.mr002out/n2/n2_scale_envelope.json"
ENVELOPE_IDENTITY = "b9e68baaab16026e9e6c57833a7a6a064419e72ddeb468211f4a46ea4a111d21"

#: (axis, instances) exactly as frozen in the sealed registration §8.
AXES = (
    ("A1", 400),   # Hessian conditioning
    ("A2", 600),   # iterative-solver burden / convergence stress
    ("A3", 400),   # constraint tightness
    ("A4", 400),   # equality-slack scarcity (the repair absorber)
    ("A5", 300),   # active-set size
    ("A6", 200),   # structurally empty A_ub rows
    ("A7", 300),   # boundary optima
    ("A8", 400),   # wide-n scaling
)


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def _load_envelope() -> tuple[float, float]:
    """The registered target-scale envelope, DERIVED from the hash-bound development corpus.

    Its own record identity is re-verified here, so the generator cannot silently drift onto a
    hand-edited envelope. Typing the constant would replace one discretionary choice with another.
    """
    with open(ENVELOPE) as fh:
        rec = json.load(fh)
    claimed = rec.pop("record_identity_sha256")
    got = hashlib.sha256(
        (json.dumps(rec, sort_keys=True, indent=1) + "\n").encode("ascii")).hexdigest()
    if got != claimed or claimed != ENVELOPE_IDENTITY:
        raise SystemExit(f"ABORT: scale-envelope identity {got} != expected {ENVELOPE_IDENTITY}")
    if rec["authoritative_source"]["corpus_hash"] != (
            "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"):
        raise SystemExit("ABORT: scale envelope not derived from the registered corpus")
    return float(rec["T_MAX_REGISTERED"]), float(rec["T_MIN_REGISTERED"])


T_MAX_REGISTERED, T_MIN_REGISTERED = _load_envelope()


def _targets(rng, n, kappa):
    """t > 0 with max(t)/min(t) == kappa, ANCHORED AT THE REGISTERED UPPER SCALE.

    CORRECTED (owner ruling 2026-08-19, N2 generator specification defect). The original form drew a
    lower anchor and multiplied UP by kappa, so conditioning and absolute target scale moved
    together and t reached ~1e7 -- nine orders above the registered ceiling, where an ABSOLUTE
    1e-10 signed-gap band cannot be met by any double-precision solver. It measured scale, not
    conditioning.

    kappa(H) = max(t)/min(t), so the requested conditioning is obtained by driving t_min DOWN while
    t_max stays inside the registered economic scale. Per the ruling the absolute UPPER scale is the
    invariant; synthetic t_min MAY fall below the historical minimum, because that is the stress
    mechanism itself and holding it would cap kappa at ~1.7e6 and delete the axis.
    """
    t_max = T_MAX_REGISTERED * 10.0 ** rng.uniform(-2.0, 0.0)
    t_min = t_max / kappa
    t = np.exp(np.linspace(np.log(t_min), np.log(t_max), n))
    return t[rng.permutation(n)]


def _equality_row(rng, n, magnitude_span):
    """Signed sector-neutrality row. `magnitude_span` sweeps coefficient magnitudes (axis A4)."""
    sign = np.where(rng.random(n) < 0.5, -1.0, 1.0)
    if len(np.unique(sign)) == 1:          # both signs must be present or z0 = 0 is forced
        sign[rng.integers(0, n)] *= -1.0
    mag = 10.0 ** rng.uniform(-magnitude_span, magnitude_span, size=n) if magnitude_span else np.ones(n)
    return (sign * mag).reshape(1, n)


def _feasible_point(rng, t, A_eq, interior):
    """z0 with A_eq z0 = 0 and 0 <= z0 <= t. `interior` in (0, 0.5] sets how far off the bounds."""
    a = A_eq[0]
    theta = np.full(len(t), float(interior))
    z0 = theta * t
    pos, neg = a > 0, a < 0
    sp, sn = float(a[pos] @ z0[pos]), float(-a[neg] @ z0[neg])
    if sp == 0.0 or sn == 0.0:
        return np.zeros_like(t)
    if sp > sn:
        z0[pos] *= sn / sp
    else:
        z0[neg] *= sp / sn
    return np.clip(z0, 0.0, t)


def _instance(rng, axis):
    """One stress instance for `axis`, plus the parameters that produced it."""
    p: dict = {"axis": axis}

    if axis == "A1":                                   # conditioning swept 1e2 .. 1e10
        n = int(rng.integers(5, 40))
        kappa = 10.0 ** rng.uniform(2, 10)
        m_ub, dense, slack_dec, interior, span, empty, boundary = 25, 0.35, 3.0, 0.5, 0.0, 0, 0.0
    elif axis == "A2":                                 # convergence burden, implementation-agnostic
        n = int(rng.integers(45, 90))
        kappa = 10.0 ** rng.uniform(2, 6)
        m_ub, dense, slack_dec, interior, span, empty, boundary = 60, 0.95, 8.0, 0.5, 0.0, 0, 0.0
    elif axis == "A3":                                 # slack decades 1e-6 .. 1e-13
        n = int(rng.integers(5, 35))
        kappa = 10.0 ** rng.uniform(1, 5)
        m_ub, dense, slack_dec, interior, span, empty, boundary = 30, 0.5, rng.uniform(6, 13), 0.5, 0.0, 0, 0.0
    elif axis == "A4":                                 # repair-absorber scarcity
        n = int(rng.integers(5, 35))
        kappa = 10.0 ** rng.uniform(1, 5)
        m_ub, dense, slack_dec, span, empty, boundary = 25, 0.4, 4.0, rng.uniform(1, 5), 0, 0.0
        interior = 10.0 ** rng.uniform(-6, -2)         # z0 crushed toward the lower bound
    elif axis == "A5":                                 # active-set size swept 0 .. 1
        n = int(rng.integers(5, 40))
        kappa = 10.0 ** rng.uniform(1, 5)
        m_ub, dense, slack_dec, interior, span, empty = 30, 0.5, 4.0, 0.5, 0.0, 0
        boundary = 0.0
        p["active_fraction"] = float(rng.random())
    elif axis == "A6":                                 # structurally empty A_ub rows
        n = int(rng.integers(4, 30))
        kappa = 10.0 ** rng.uniform(1, 5)
        m_ub, dense, slack_dec, interior, span, boundary = 25, 0.5, 4.0, 0.5, 0.0, 0.0
        empty = int(rng.integers(1, 6))
    elif axis == "A7":                                 # optimum pinned at box bounds
        n = int(rng.integers(5, 35))
        kappa = 10.0 ** rng.uniform(1, 5)
        m_ub, dense, slack_dec, interior, span, empty = 25, 0.5, 4.0, 0.5, 0.0, 0
        boundary = float(rng.uniform(0.2, 0.7))
    else:                                              # A8 wide-n scaling
        n = int(rng.integers(60, 140))
        kappa = 10.0 ** rng.uniform(1, 5)
        m_ub, dense, slack_dec, interior, span, empty, boundary = 40, 0.5, 4.0, 0.5, 0.0, 0, 0.0

    kappa = min(kappa, KAPPA_MAX * 0.5)
    t = _targets(rng, n, kappa)
    upper = t.copy()                                   # registered population invariant
    A_eq = _equality_row(rng, n, span)
    b_eq = np.zeros(1)
    z0 = _feasible_point(rng, t, A_eq, interior)

    if boundary:
        # A7: pin coordinates AT the box bounds, then solve the equality EXACTLY on the free
        # coordinates rather than nudging and hoping. Pinning first and repairing afterwards cannot
        # work in general -- the residual may simply be unreachable from the remaining box -- so the
        # pinned set is shrunk deterministically until the residual IS reachable. The axis is never
        # silently weakened: the realised pin count is recorded.
        a = A_eq[0]
        order = rng.permutation(n)
        k = max(2, int(boundary * n))
        while k >= 2:
            pin = order[:k]
            z_try = z0.copy()
            half = k // 2
            z_try[pin[:half]] = 0.0
            z_try[pin[half:]] = t[pin[half:]]
            free = np.setdiff1d(np.arange(n), pin)
            if len(free) == 0:
                k -= 2
                continue
            target = -float(a[pin] @ z_try[pin])          # what the free block must contribute
            af, tf = a[free], t[free]
            hi = float(np.sum(np.where(af > 0, af * tf, 0.0)))   # max reachable
            lo = float(np.sum(np.where(af < 0, af * tf, 0.0)))   # min reachable
            if lo - 1e-18 <= target <= hi + 1e-18:
                z_free = np.zeros(len(free))
                if target >= 0 and hi > 0:
                    z_free[af > 0] = (target / hi) * tf[af > 0]
                elif target < 0 and lo < 0:
                    z_free[af < 0] = (target / lo) * tf[af < 0]
                z_try[free] = np.clip(z_free, 0.0, tf)
                # absorb residual rounding on the single largest-capacity free coordinate
                r = float(a @ z_try)
                if r != 0.0:
                    j = free[int(np.argmax(np.abs(af) * tf))]
                    adj = z_try[j] - r / a[j]
                    if 0.0 <= adj <= t[j]:
                        z_try[j] = adj
                z0 = z_try
                p["boundary_pinned"] = int(k)
                break
            k -= 2
        p["boundary_fraction"] = float(boundary)

    A_ub = rng.normal(0.0, 1.0, size=(m_ub, n))
    A_ub[rng.random((m_ub, n)) > dense] = 0.0
    if empty:
        A_ub[rng.permutation(m_ub)[:empty]] = 0.0
        p["empty_rows"] = int(empty)

    base = A_ub @ z0
    scale = float(np.max(np.abs(base))) or 1.0
    slack = scale * 10.0 ** (-np.asarray(slack_dec, dtype=float))
    s = np.full(m_ub, slack, dtype=float)
    if axis == "A5":                                   # a fraction of rows exactly tight at z0
        k = int(p["active_fraction"] * m_ub)
        s[rng.permutation(m_ub)[:k]] = 0.0
    b_ub = base + s
    zero_rows = ~A_ub.any(axis=1)
    b_ub[zero_rows] = np.abs(b_ub[zero_rows])          # 0 <= b_j keeps an empty row satisfiable

    p.update({"n": int(n), "m_ub": int(m_ub), "kappa": float(t.max() / t.min()),
              "slack_decades": float(np.mean(np.asarray(slack_dec, dtype=float))),
              "interior": float(interior), "eq_magnitude_span": float(span)})
    return (t, A_ub, b_ub, A_eq, b_eq, upper), z0, p


def verify(rec, z0) -> str | None:
    """Registered structural contract + exact feasibility of the constructed point."""
    t, A_ub, b_ub, A_eq, b_eq, upper = rec
    n = len(t)
    if not np.all(t > 0):
        return "t not strictly positive"
    if float(t.max()) > T_MAX_REGISTERED:
        return f"t_max {t.max():.6e} exceeds T_MAX_REGISTERED {T_MAX_REGISTERED:.6e}"
    if A_eq.shape[0] != 1:
        return f"meq != 1 (got {A_eq.shape[0]})"
    if not np.array_equal(upper, t):
        return "upper != t elementwise"
    for name, a in (("A_ub", A_ub), ("b_ub", b_ub), ("A_eq", A_eq), ("b_eq", b_eq), ("upper", upper)):
        if not np.all(np.isfinite(a)):
            return f"{name} not finite"
    if A_ub.shape != (len(b_ub), n) or A_eq.shape != (1, n) or upper.shape != (n,):
        return "shape mismatch"
    kappa = float(t.max() / t.min())
    if kappa > KAPPA_MAX:
        return f"kappa {kappa:.3e} > {KAPPA_MAX:.0e}"
    if not (np.all(z0 >= -0.0) and np.all(z0 <= t + 0.0)):
        return "constructed point outside the box"
    resid = float((A_eq @ z0)[0] - b_eq[0])
    if abs(resid) > 1e-9 * max(1.0, float(np.abs(A_eq).max() * t.max())):
        return "constructed point violates the equality"
    if np.any(A_ub @ z0 - b_ub > 1e-12 * max(1.0, float(np.abs(b_ub).max()))):
        return "constructed point violates an inequality"
    return None


def main() -> int:
    rng = np.random.Generator(np.random.PCG64(SEED))
    payload: dict = {}
    hashes: list[str] = []
    params: list[dict] = []
    idx = 0

    for axis, count in AXES:
        for _ in range(count):
            rec, z0, p = _instance(rng, axis)
            bad = verify(rec, z0)
            if bad is not None:
                raise SystemExit(f"ABORT: generator bug on {axis} instance {idx}: {bad}")
            for k, a in zip(("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"), rec, strict=True):
                payload[f"{idx}_{k}"] = np.ascontiguousarray(np.asarray(a, dtype=np.float64))
            h = _hash_instance(*rec)
            payload[f"{idx}_hash"] = np.array(h)
            hashes.append(h)
            p["index"] = idx
            params.append(p)
            idx += 1
        print(f"  {axis}: {count} instances generated and contract-verified", flush=True)

    population_hash = hashlib.sha256("|".join(hashes).encode()).hexdigest()
    payload["n_instances"] = np.array(idx)
    payload["population_hash"] = np.array(population_hash)
    payload["seed"] = np.array(SEED)
    payload["T_MAX_REGISTERED"] = np.array(T_MAX_REGISTERED)
    payload["envelope_identity"] = np.array(ENVELOPE_IDENTITY)

    os.makedirs(OUT_DIR, exist_ok=True)
    np.savez_compressed(os.path.join(OUT_DIR, "stress.npz"), **payload)
    with open(os.path.join(OUT_DIR, "n2_population.json"), "w") as fh:
        json.dump({"seed": SEED, "instances": idx, "population_hash": population_hash,
                   "axes": {a: c for a, c in AXES}, "parameters": params,
                   "generator_revision": "v1.1 — corrected target-scale anchoring",
                   "T_MAX_REGISTERED": T_MAX_REGISTERED,
                   "T_MIN_REGISTERED": T_MIN_REGISTERED,
                   "scale_envelope_identity": ENVELOPE_IDENTITY}, fh, indent=1,
                  sort_keys=True)

    print(f"\ninstances        {idx}")
    print(f"population_hash  {population_hash}")
    ns = [p["n"] for p in params]
    ks = [p["kappa"] for p in params]
    print(f"n     min/med/max {min(ns)}/{int(np.median(ns))}/{max(ns)}")
    print(f"kappa min/med/max {min(ks):.2e}/{np.median(ks):.2e}/{max(ks):.2e}")
    tmaxs = [float(payload[f"{i}_t"].max()) for i in range(idx)]
    print(f"t_max max         {max(tmaxs):.6e}  (ceiling {T_MAX_REGISTERED:.6e})")
    print(f"within envelope   {sum(1 for v in tmaxs if v <= T_MAX_REGISTERED)}/{idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
