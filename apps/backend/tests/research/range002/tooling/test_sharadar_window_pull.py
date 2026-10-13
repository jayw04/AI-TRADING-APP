"""sharadar_window_pull on a MOCK transport only (no network, no real key). Fixture rows are
synthetic; the numbers asserted describe the fixture, never a vendor table."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"
sys.path.insert(0, str(SCRIPTS))
import sharadar_window_pull as sp  # noqa: E402

from app.licensing.envelope import write_sidecar  # noqa: E402
from app.licensing.gate import PersonalScopeBlocked  # noqa: E402
from app.licensing.output import export_file_for_external_use  # noqa: E402

KEY = "SECRET-KEY-VALUE-123456"
PERM_REF = "synthetic-test-ref (not a real record)"
PERM_SCOPE = "tickers, actions, sep (synthetic)"

TICKERS_COLS = [
    {"name": "table", "type": "String"},
    {"name": "permaticker", "type": "Integer"},
    {"name": "ticker", "type": "String"},
    {"name": "name", "type": "String"},
    {"name": "isdelisted", "type": "String"},
    {"name": "firstpricedate", "type": "Date"},
    {"name": "lastpricedate", "type": "Date"},
    {"name": "lastupdated", "type": "Date"},
]
TICKERS_ROWS = [
    ["SEP", 1, "AAA", "Alpha", "N", "2010-01-04", "2026-06-12", "2026-06-12"],
    ["SF1", 1, "AAA", "Alpha", "N", "2010-01-04", "2026-06-12", "2026-06-12"],
    ["SEP", 2, "REUS", "Old", "Y", "2010-01-04", "2012-01-03", "2012-01-03"],
    ["SEP", 3, "REUS", "New", "N", "2018-01-02", "2026-06-12", "2026-06-12"],
    ["SEP", 5, "OLDN", "Rn", "Y", "2010-01-04", "2017-06-30", "2017-06-30"],
    ["SEP", 5, "NEWN", "Rn", "N", "2017-07-01", None, "2026-06-12"],
]
ACTIONS_COLS = [
    {"name": "date", "type": "Date"},
    {"name": "action", "type": "String"},
    {"name": "ticker", "type": "String"},
    {"name": "value", "type": "BigDecimal(34,11)"},
]
ACTIONS_ROWS = [
    ["2016-02-01", "split", "AAA", 2.0],
    ["2012-01-03", "delisted", "REUS", None],
]
SEP_COLS = [
    {"name": "ticker", "type": "String"},
    {"name": "date", "type": "Date"},
    {"name": "open", "type": "BigDecimal(34,11)"},
    {"name": "high", "type": "BigDecimal(34,11)"},
    {"name": "low", "type": "BigDecimal(34,11)"},
    {"name": "close", "type": "BigDecimal(34,11)"},
    {"name": "volume", "type": "BigDecimal(34,11)"},
    {"name": "closeadj", "type": "BigDecimal(34,11)"},
    {"name": "closeunadj", "type": "BigDecimal(34,11)"},
    {"name": "lastupdated", "type": "Date"},
]


def sep_rows(n: int) -> list[list[Any]]:
    out: list[list[Any]] = []
    for i in range(n):
        day = 4 + i  # 2016-01-04 ...
        t = ["AAA", "BBB"][i % 2]
        out.append(
            [t, f"2016-01-{day:02d}", 1.5, 2.0, 1.0, 1.75, 1000.0 + i, 1.7, 1.75, "2016-02-01"]
        )
    return out


class Fake:
    """A mock Nasdaq Data Link: serves ``page_size`` rows per page with cursor ids."""

    def __init__(self, page_size: int = 2, fail_first: dict[str, int] | None = None) -> None:
        self.page_size = page_size
        self.calls: list[httpx.Request] = []
        self.fail_first = dict(fail_first or {})
        self.tables: dict[str, tuple[list[dict[str, str]], list[list[Any]]]] = {
            "TICKERS": (TICKERS_COLS, TICKERS_ROWS),
            "ACTIONS": (ACTIONS_COLS, ACTIONS_ROWS),
            "SEP": (SEP_COLS, sep_rows(7)),
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "data.nasdaq.com"
        table = request.url.path.rsplit("/", 1)[1].removesuffix(".json")
        if self.fail_first.get(table, 0) > 0:
            self.fail_first[table] -= 1
            return httpx.Response(
                503, text=f"upstream busy api_key={request.url.params['api_key']}"
            )
        cols, rows = self.tables[table]
        q = request.url.params
        if table == "SEP":
            lo, hi = q["date.gte"], q["date.lte"]
            rows = [r for r in rows if lo <= r[1] <= hi]
        start = int(q["qopts.cursor_id"].split("-")[1]) if "qopts.cursor_id" in q else 0
        chunk = rows[start : start + self.page_size]
        nxt = start + self.page_size
        meta = {"next_cursor_id": f"cur-{nxt}" if nxt < len(rows) else None}
        return httpx.Response(
            200, json={"datatable": {"data": chunk, "columns": cols}, "meta": meta}
        )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(sp, "_sleep", slept.append)
    return slept


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    d = tmp_path / "dest"
    d.mkdir()
    return d


def do_pull(
    dest: Path,
    fake: Callable[[httpx.Request], httpx.Response],
    export_id: str = "pull-1",
    **over: Any,
) -> Path:
    kw: dict[str, Any] = {
        "dest_root": dest,
        "export_id": export_id,
        "purpose": "synthetic test",
        "executing_identity": "tester",
        "permission_ref": PERM_REF,
        "permission_scope": PERM_SCOPE,
        "sep_date_from": "2016-01-04",
        "sep_date_to": "2016-01-08",
        "max_pages": 50,
        "transport": httpx.MockTransport(fake),
        "api_key": KEY,
    }
    kw.update(over)
    return sp.run_pull(**kw)


def manifest_of(out: Path) -> dict[str, Any]:
    m: dict[str, Any] = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    return m


def test_pagination_follows_cursor_across_pages(dest: Path) -> None:
    fake = Fake(page_size=2)
    out = do_pull(dest, fake)
    m = manifest_of(out)
    by = {f["table"]: f for f in m["files"]}
    assert by["tickers"]["rows"] == 6 and m["pages"]["tickers"] == 3
    assert by["actions"]["rows"] == 2 and m["pages"]["actions"] == 1
    assert by["sep"]["rows"] == 5 and m["pages"]["sep"] == 3  # window keeps 5 of 7 rows
    cursors = [c.url.params.get("qopts.cursor_id") for c in fake.calls if "TICKERS" in str(c.url)]
    assert cursors == [None, "cur-2", "cur-4"]
    assert (out / "EXPORT_COMPLETE.json").is_file() and not (dest / ".staging-pull-1").exists()


def test_tickers_is_unfiltered_and_keeps_all_columns_and_table_values(dest: Path) -> None:
    fake = Fake()
    out = do_pull(dest, fake)
    tk = [c for c in fake.calls if "/TICKERS.json" in str(c.url)]
    assert set(tk[0].url.params.keys()) == {"api_key"}
    con = duckdb.connect(":memory:")
    rows = con.execute(
        f"SELECT \"table\", COUNT(*) FROM read_parquet('{(out / 'tickers.parquet').as_posix()}') "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert rows == [("SEP", 5), ("SF1", 1)]
    m = manifest_of(out)
    tk_file = next(f for f in m["files"] if f["table"] == "tickers")
    assert tk_file["columns"] == [c["name"] for c in TICKERS_COLS]


def test_actions_unfiltered_and_sep_date_filter_params(dest: Path) -> None:
    fake = Fake()
    do_pull(dest, fake)
    ac = next(c for c in fake.calls if "/ACTIONS.json" in str(c.url))
    assert set(ac.url.params.keys()) == {"api_key"}
    sep = [c for c in fake.calls if "/SEP.json" in str(c.url)]
    assert all(c.url.params["date.gte"] == "2016-01-04" for c in sep)
    assert all(c.url.params["date.lte"] == "2016-01-08" for c in sep)
    assert all(c.url.params["api_key"] == KEY for c in sep)  # the key travels only on the wire
    assert all("ticker" not in c.url.params for c in sep)


def test_retry_on_transient_error_with_backoff(dest: Path, no_sleep: list[float]) -> None:
    fake = Fake(page_size=10, fail_first={"ACTIONS": 2})
    out = do_pull(dest, fake)
    assert manifest_of(out)["pages"]["actions"] == 1
    assert len([c for c in fake.calls if "/ACTIONS.json" in str(c.url)]) == 3
    assert [s for s in no_sleep if s >= 1.0] == [1.0, 2.0]


def test_retry_exhaustion_fails_closed_without_publish_and_without_key(dest: Path) -> None:
    fake = Fake(fail_first={"ACTIONS": 99})
    with pytest.raises(sp.PullError) as ei:
        do_pull(dest, fake)
    assert KEY not in str(ei.value)
    assert not (dest / "pull-1").exists()
    failed = (dest / ".staging-pull-1" / "EXPORT_FAILED.json").read_text(encoding="utf-8")
    assert KEY not in failed
    assert not (dest / ".staging-pull-1" / "EXPORT_COMPLETE.json").exists()


def test_non_retryable_4xx_fails_fast(dest: Path) -> None:
    n = [0]

    def h(request: httpx.Request) -> httpx.Response:
        n[0] += 1
        return httpx.Response(403, text="forbidden api_key=" + request.url.params["api_key"])

    with pytest.raises(sp.PullError) as ei:
        do_pull(dest, h)
    assert n[0] == 1 and KEY not in str(ei.value) and "403" in str(ei.value)


def test_transport_error_is_scrubbed(dest: Path) -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom " + str(request.url), request=request)

    with pytest.raises(sp.PullError) as ei:
        do_pull(dest, h)
    text = str(ei.value) + repr(ei.value) + str(ei.value.__cause__) + str(ei.value.__context__)
    assert KEY not in text
    assert KEY not in (dest / ".staging-pull-1" / "EXPORT_FAILED.json").read_text(encoding="utf-8")


def test_key_never_in_any_published_file(dest: Path) -> None:
    out = do_pull(dest, Fake())
    for p in out.iterdir():
        assert KEY.encode() not in p.read_bytes(), p.name
    blob = (out / "manifest.json").read_text(encoding="utf-8")
    assert "api_key" not in blob.replace("never recorded", "")
    assert manifest_of(out)["source"]["key"].startswith("read from environment variable")


def test_missing_env_key_refuses_before_any_request_or_staging(
    dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(sp.KEY_ENV, raising=False)
    fake = Fake()
    with pytest.raises(sp.PullError, match="not set"):
        do_pull(dest, fake, api_key=None)
    assert fake.calls == [] and list(dest.iterdir()) == []


def test_key_is_read_from_environment(dest: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(sp.KEY_ENV, "ENVKEY-9876")
    fake = Fake()
    do_pull(dest, fake, api_key=None)
    assert all(c.url.params["api_key"] == "ENVKEY-9876" for c in fake.calls)


def test_cli_has_no_key_argument() -> None:
    opts = {a.dest for a in sp.build_parser()._actions}
    assert not any("key" in o for o in opts)


def test_overwrite_refused_for_existing_export_and_staging(dest: Path) -> None:
    out = do_pull(dest, Fake())
    before = (out / "manifest.json").read_bytes()
    fake = Fake()
    with pytest.raises(sp.PullError, match="already exists"):
        do_pull(dest, fake)
    assert fake.calls == [] and (out / "manifest.json").read_bytes() == before
    (dest / ".staging-other").mkdir()
    with pytest.raises(sp.PullError, match="staging"):
        do_pull(dest, fake, export_id="other")
    assert fake.calls == []


def test_failure_leaves_no_published_dir(dest: Path) -> None:
    fake = Fake(fail_first={"SEP": 99})
    with pytest.raises(sp.PullError):
        do_pull(dest, fake)
    assert sorted(p.name for p in dest.iterdir()) == [".staging-pull-1"]
    assert (dest / ".staging-pull-1" / "EXPORT_FAILED.json").is_file()


def test_max_pages_is_enforced_and_fails_closed(dest: Path) -> None:
    fake = Fake(page_size=1)  # TICKERS needs 6 pages
    with pytest.raises(sp.PullError, match="max-pages"):
        do_pull(dest, fake, max_pages=3)
    assert not (dest / "pull-1").exists()
    assert len([c for c in fake.calls if "/TICKERS.json" in str(c.url)]) == 3


def test_cursor_loop_is_refused(dest: Path) -> None:
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "datatable": {"data": [["x"]], "columns": [{"name": "c", "type": "String"}]},
                "meta": {"next_cursor_id": "same"},
            },
        )

    with pytest.raises(sp.PullError, match="cursor repeated"):
        do_pull(dest, h)


def test_empty_table_and_out_of_window_rows_refused(dest: Path) -> None:
    fake = Fake()
    fake.tables["ACTIONS"] = (ACTIONS_COLS, [])
    with pytest.raises(sp.PullError, match="zero rows"):
        do_pull(dest, fake, export_id="e1")

    base = Fake()

    def h(request: httpx.Request) -> httpx.Response:
        if "/SEP.json" in str(request.url):  # vendor ignores the date filter
            cols, rows = base.tables["SEP"]
            return httpx.Response(
                200, json={"datatable": {"data": rows, "columns": cols}, "meta": {}}
            )
        return base(request)

    with pytest.raises(sp.PullError, match="outside the requested window"):
        do_pull(dest, h, export_id="e2")


def test_sep_missing_requested_column_refused(dest: Path) -> None:
    fake = Fake()
    cols = [c for c in SEP_COLS if c["name"] != "closeunadj"]
    fake.tables["SEP"] = (cols, [r[:8] + r[9:] for r in sep_rows(7)])
    with pytest.raises(sp.PullError, match="closeunadj"):
        do_pull(dest, fake)


def test_manifest_fields_validated(dest: Path) -> None:
    out = do_pull(dest, Fake())
    m = manifest_of(out)
    assert sp.validate_manifest(m) == []
    assert m["license_status"] == "UNKNOWN" and m["permission_verified"] is False
    assert m["permission_basis_claimed"]["ref"] == PERM_REF
    assert (
        m["script_sha256"]
        == hashlib.sha256((SCRIPTS / "sharadar_window_pull.py").read_bytes()).hexdigest()
    )
    assert m["source"]["endpoints"] == [
        f"{sp.NDL_BASE}/TICKERS.json",
        f"{sp.NDL_BASE}/ACTIONS.json",
        f"{sp.NDL_BASE}/SEP.json",
    ]
    assert m["requests"]["sep"]["params"] == {"date.gte": "2016-01-04", "date.lte": "2016-01-08"}
    sep = next(f for f in m["files"] if f["table"] == "sep")
    assert sep["date_bounds"]["date"] == {"min": "2016-01-04", "max": "2016-01-08"}
    assert m["vendor_lastupdated_bounds"]["sep"] == {"min": "2016-02-01", "max": "2016-02-01"}
    assert m["requested_sep_window"]["inclusive"] is True
    for field in sp.REQUIRED_FILE_FIELDS:
        assert all(f[field] not in (None, "") for f in m["files"] if field != "date_bounds")
    for bad in ({"permission_verified": True}, {"license_status": "COMMERCIAL_OK"}, {"files": []}):
        assert sp.validate_manifest({**m, **bad})
    broken = {k: v for k, v in m.items() if k != "tickers_feasibility"}
    assert sp.validate_manifest(broken)


def test_tickers_feasibility_facts(dest: Path) -> None:
    m = manifest_of(do_pull(dest, Fake()))
    f = m["tickers_feasibility"]
    assert f["rows"] == 6 and f["distinct_permaticker"] == 4 and f["distinct_ticker"] == 4
    assert f["tickers_under_more_than_one_permaticker"] == 1  # REUS
    assert f["permatickers_with_more_than_one_ticker"] == 1  # permaticker 5
    assert f["rows_by_table"] == {"SEP": 5, "SF1": 1}
    iv = f["per_row_price_date_interval"]
    assert iv["columns_present"] is True and iv["rows_with_both"] == 5 and iv["rows_total"] == 6
    assert "NOT asserted" in f["note"]


def test_logical_hash_is_reproducible_and_ignores_byte_layout(dest: Path) -> None:
    a = manifest_of(do_pull(dest, Fake(page_size=2), "a"))
    b = manifest_of(do_pull(dest, Fake(page_size=3), "b"))  # different paging, same content
    la = {f["table"]: f["logical_sha256"] for f in a["files"]}
    lb = {f["table"]: f["logical_sha256"] for f in b["files"]}
    assert la == lb and all(len(v) == 64 for v in la.values())
    assert a["pages"] != b["pages"]
    rows, _, h = sp.read_parquet_summary(
        dest / "a" / "actions.parquet", ["date", "action", "ticker", "value"], []
    )
    assert rows == 2 and h == la["actions"]


def test_sidecars_agree_with_licensing_module_and_seam_refuses(dest: Path, tmp_path: Path) -> None:
    out = do_pull(dest, Fake())
    assert (out / "README_PU1.txt").is_file()
    targets = sorted(out.glob("*.parquet")) + [out / "manifest.json"]
    assert len(targets) == 4
    for f in targets:
        mine = (out / (f.name + ".license.json")).read_bytes()
        ref = tmp_path / f"ref-{f.name}"
        ref.write_bytes(f.read_bytes())
        write_sidecar(ref, ["sharadar"])
        assert (tmp_path / f"ref-{f.name}.license.json").read_bytes() == mine
        with pytest.raises(PersonalScopeBlocked):
            export_file_for_external_use(f, tmp_path / "ext" / f.name)
        assert not (tmp_path / "ext" / f.name).exists()


def test_dry_plan_makes_no_http_call_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("network used in --dry-plan")

    monkeypatch.setattr(httpx.Client, "send", boom)
    monkeypatch.setattr(httpx, "Client", boom)
    monkeypatch.setenv(sp.KEY_ENV, KEY)
    dest = tmp_path / "not-created"
    rc = sp.main(
        [
            "--dest-root", str(dest), "--export-id", "x1", "--purpose", "p",
            "--executing-identity", "me", "--permission-ref", "r", "--permission-scope", "s",
            "--sep-date-from", "2016-01-01", "--sep-date-to", "2016-03-31", "--max-pages", "9",
            "--dry-plan",
        ]
    )  # fmt: skip
    out = capsys.readouterr()
    assert rc == 0 and not dest.exists()
    assert KEY not in out.out + out.err
    assert "SHARADAR/TICKERS.json?api_key=***REDACTED***" in out.out
    assert "date.gte=2016-01-01&date.lte=2016-03-31&api_key=***REDACTED***" in out.out
    assert "cap 9 pages" in out.out and "present" in out.out


def test_required_arguments_have_no_defaults() -> None:
    p = sp.build_parser()
    req = {a.dest for a in p._actions if a.required}
    assert req == {
        "dest_root", "export_id", "purpose", "executing_identity", "permission_ref",
        "permission_scope", "sep_date_from", "sep_date_to", "max_pages",
    }  # fmt: skip


def test_bad_inputs_refused(dest: Path) -> None:
    fake = Fake()
    for over, msg in (
        ({"sep_date_from": "2016-02-01", "sep_date_to": "2016-01-01"}, "<="),
        ({"sep_date_from": "2016/01/01"}, "YYYY-MM-DD"),
        ({"max_pages": 0}, "max-pages"),
        ({"export_id": "../evil"}, "export id"),
        ({"permission_ref": "  "}, "permission-ref"),
        ({"dest_root": dest / "missing"}, "existing directory"),
    ):
        with pytest.raises(sp.PullError, match=msg):
            do_pull(dest, fake, **over)
    assert fake.calls == []


def test_script_runs_isolated_dry_plan_under_python_dash_i(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable, "-I", str(SCRIPTS / "sharadar_window_pull.py"),
            "--dest-root", str(tmp_path), "--export-id", "x", "--purpose", "p",
            "--executing-identity", "me", "--permission-ref", "r", "--permission-scope", "s",
            "--sep-date-from", "2016-01-01", "--sep-date-to", "2016-03-31", "--max-pages", "5",
            "--dry-plan",
        ],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    assert "DRY PLAN" in r.stdout
