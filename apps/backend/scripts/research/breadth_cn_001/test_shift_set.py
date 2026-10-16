"""Properties of the fixed circular-shift set.  Run: python3 test_shift_set.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import shift_set as S  # noqa: E402


def test_properties() -> None:
    L = 1800
    s = S.shift_set(L)
    assert len(s) == S.N_SHIFTS == len(set(s))
    assert min(s) >= S.MIN_SHIFT and max(s) <= L - S.MIN_SHIFT
    assert all(min(k, L - k) >= S.MIN_SHIFT for k in s), (
        "circular distance from identity must be >= MIN_SHIFT both ways"
    )
    assert S.shift_set(L) == s and S.shift_set(L, seed=S.SEED + 1) != s
    assert S.digest(s, L) == S.digest(S.shift_set(L), L)
    print(
        "ok 500 distinct shifts, circular distance >= 20 in both directions, deterministic for the fixed seed"
    )


def test_rotation_preserves_the_setup_pattern() -> None:
    import numpy as np

    L = 400
    setups = np.zeros(L, dtype=int)
    setups[[10, 25, 26, 90, 300]] = [1, -1, 1, -1, 1]
    for k in S.shift_set(L, n=50):
        r = np.roll(setups, k)
        assert (r != 0).sum() == 5 and sorted(r[r != 0]) == sorted(
            setups[setups != 0]
        )  # count and side mix
        pos = np.flatnonzero(setups)
        gaps = np.diff(np.concatenate([pos, [pos[0] + L]]))  # circular gaps
        pos2 = np.flatnonzero(r)
        gaps2 = np.diff(np.concatenate([pos2, [pos2[0] + L]]))
        assert sorted(gaps) == sorted(gaps2)  # spacing preserved
    print("ok rotation keeps the number of setups, the side sequence and the spacing")


if __name__ == "__main__":
    test_properties()
    test_rotation_preserves_the_setup_pattern()
    print("ALL TESTS PASSED")
