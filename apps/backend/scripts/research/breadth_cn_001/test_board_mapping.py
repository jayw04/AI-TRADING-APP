"""Every A-share symbol must map to a known board; the two board mappers must agree.
Run: python3 test_board_mapping.py

Guards against enumerated-prefix lists going stale (302132 fell through to OTHER; 689009 and 302132 were dropped from the
pull universe).  The real-master check runs when the local security-master store exists and is skipped otherwise."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import build_indicator as bi  # noqa: E402
import pull_baostock as P  # noqa: E402

KNOWN = {"SH_MAIN", "SZ_MAIN", "CHINEXT", "STAR"}
SYNTHETIC = {
    "600000": "SH_MAIN", "601166": "SH_MAIN", "603000": "SH_MAIN", "605001": "SH_MAIN",
    "688001": "STAR", "689009": "STAR",
    "000001": "SZ_MAIN", "001872": "SZ_MAIN", "002001": "SZ_MAIN", "003816": "SZ_MAIN",
    "300001": "CHINEXT", "301567": "CHINEXT", "302132": "CHINEXT",
}  # fmt: skip
STORE = Path.home() / ".cn_ashare" / "myquant_free" / "cn_ashare_myquant_free.duckdb"


def test_synthetic_prefix_families() -> None:
    codes = pd.Series(list(SYNTHETIC))
    got_bi = dict(zip(codes, bi.board_from_code(codes), strict=True))
    for code, board in SYNTHETIC.items():
        assert got_bi[code] == board, (code, got_bi[code], board)
        assert P.board_of(code) == board, (code, P.board_of(code), board)
        assert P.A_SHARE_CODE.match(code), f"{code} would be dropped from the pull universe"
    for code in (
        "900901",
        "200002",
        "510300",
        "399001",
    ):  # B-share, fund, index: must NOT enter the A-share universe
        assert not P.A_SHARE_CODE.match(code), code
    print("ok synthetic prefix families (incl. 302132, 689009) map identically in both mappers")


def test_real_master_has_no_unknown_board() -> None:
    if not STORE.exists():
        print("skip real-master board check (store not found)")
        return
    import duckdb

    con = duckdb.connect(str(STORE), read_only=True)
    m = con.execute(
        "select symbol from ashare_symbol_master where exchange in ('SHSE','SZSE')"
    ).df()
    con.close()
    codes = m["symbol"].str[-6:]
    b1 = pd.Series(bi.board_from_code(codes).to_numpy(), index=codes.index)
    b2 = codes.map(P.board_of)
    other = codes[~b1.isin(KNOWN)].tolist()
    assert not other, f"symbols mapped to an unknown board: {other[:10]}"
    assert (b1 == b2).all(), codes[b1 != b2].tolist()[:10]
    assert codes.str.match(P.A_SHARE_CODE).all(), codes[~codes.str.match(P.A_SHARE_CODE)].tolist()[
        :10
    ]
    print(
        f"ok all {len(m)} master symbols map to a known board and into the pull universe: {b1.value_counts().to_dict()}"
    )


if __name__ == "__main__":
    test_synthetic_prefix_families()
    test_real_master_has_no_unknown_board()
    print("ALL TESTS PASSED")
