"""R1-L1b: freeze refuses non-distinct sign-off role identifiers.

Scope and limits (Level 1): these tests exercise *distinct role identifier strings only*.
Identifiers are unauthenticated free text; nothing here verifies who anyone is. Real separation of
duties needs the signing design (Level 2).
"""

from __future__ import annotations

import json

import pytest

from app.research.range002.spec.loader import load_draft, load_frozen
from app.research.range002.spec.schema import (
    Signoff,
    SignoffRoleCharactersError,
    SignoffRolesNotDistinctError,
    _non_distinct_signoff_roles,
    _normalize_role_identifier,
    _signoff_invisible_char_roles,
)

from ._fixtures import complete_payload
from .test_freeze import _write, cli

ROLES = ("owner", "trading_expert", "independent_validator")
PAIRS = [
    ("owner", "trading_expert"),
    ("owner", "independent_validator"),
    ("trading_expert", "independent_validator"),
]


def _try_freeze(tmp_path, capsys, **roles):
    payload = complete_payload()
    payload["signoff"].update(roles)
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    return rc, out, capsys.readouterr().err


@pytest.mark.parametrize(
    "a, b",
    [
        ("Jay Wang", "Jay Wang"),  # identical
        ("Jay Wang", "jay wang"),  # case
        ("Jay Wang", "JAY WANG"),
        ("Jay Wang", "  Jay Wang  "),  # leading/trailing whitespace
        ("Jay Wang", "Jay   Wang"),  # internal whitespace collapse
        ("Jay Wang", "Jay\t Wang"),  # tab / NBSP collapse
        ("Jay Wang", "Ｊay Wang"),  # NFKC: fullwidth J
        ("Straße", "STRASSE"),  # casefold: sharp s
        ("ﬁnn", "finn"),  # NFKC: fi ligature
        ("υ", "ϒ"),  # NFKC must precede casefold: U+03D2 only equals U+03C5 in that order
    ],
)
@pytest.mark.parametrize("pair", PAIRS)
def test_two_of_three_equal_after_normalisation_refused(tmp_path, capsys, a, b, pair):
    third = next(r for r in ROLES if r not in pair)
    roles = {pair[0]: a, pair[1]: b, third: "SYNTH-THIRD"}
    rc, out, err = _try_freeze(tmp_path, capsys, **roles)
    assert rc == 2 and not out.exists()
    assert "not distinct" in err and pair[0] in err and pair[1] in err


def test_all_three_identical_refused(tmp_path, capsys):
    rc, out, err = _try_freeze(
        tmp_path,
        capsys,
        owner="X Person",
        trading_expert="x person",
        independent_validator="X  PERSON",
    )
    assert rc == 2 and not out.exists()
    assert "owner" in err and "trading_expert" in err and "independent_validator" in err


def test_error_type_is_named_and_carries_the_colliding_roles(tmp_path):
    payload = complete_payload()
    payload["signoff"].update(owner="A", trading_expert="a ", independent_validator="B")
    spec = load_draft(_write(tmp_path / "d.json", payload))
    assert _non_distinct_signoff_roles(spec.signoff) == [("owner", "trading_expert")]
    err = SignoffRolesNotDistinctError([("owner", "trading_expert")])
    assert isinstance(err, ValueError) and err.groups == (("owner", "trading_expert"),)


def test_all_distinct_passes_and_round_trips(tmp_path, capsys):
    rc, out, _ = _try_freeze(tmp_path, capsys)  # SYNTH-OWNER / SYNTH-EXPERT / SYNTH-VALIDATOR
    assert rc == 0 and out.exists()
    view = load_frozen(out)
    assert view.is_signed and view.unusable_reasons == ()


def test_blank_still_refused_as_missing_not_as_collision(tmp_path, capsys):
    rc, out, err = _try_freeze(tmp_path, capsys, owner="   ", trading_expert="   ")
    assert rc == 2 and not out.exists()
    assert "missing" in err and "not distinct" not in err  # two blanks are 'missing', not 'equal'


def test_confusable_lookalikes_are_not_claimed_to_be_caught(tmp_path, capsys):
    # KNOWN LIMIT: NFKC does not map Cyrillic U+0430 to Latin 'a'. Homoglyph-different strings are
    # treated as distinct. This is a distinct-strings check, NOT identity verification.
    rc, out, _ = _try_freeze(tmp_path, capsys, owner="Jay Wang", trading_expert="Jаy Wang")
    assert rc == 0 and out.exists()
    assert _normalize_role_identifier("Jay Wang") != _normalize_role_identifier("Jаy Wang")


def test_normalisation_function_contract():
    assert _normalize_role_identifier("  Jay \t Wang ") == "jay wang"
    assert _normalize_role_identifier("   ") == ""


def test_load_frozen_reports_non_distinct_roles_as_unusable(tmp_path, capsys):
    # A frozen file edited after the fact (signoff is outside spec_sha256) must not read as signed.
    rc, out, _ = _try_freeze(tmp_path, capsys)
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    data["signoff"]["trading_expert"] = " synth-owner "
    out.write_text(json.dumps(data), encoding="utf-8")
    view = load_frozen(out)
    assert view.is_signed is False
    assert any("not distinct" in r and "owner" in r for r in view.unusable_reasons)


def test_signoff_still_outside_hash_scope(tmp_path, capsys):
    rc1, out1, _ = _try_freeze(tmp_path, capsys)
    assert rc1 == 0
    h1 = load_frozen(out1).spec_sha256
    sub = tmp_path / "b"
    sub.mkdir()
    rc2, out2, _ = _try_freeze(sub, capsys, owner="OTHER-OWNER")
    assert rc2 == 0 and load_frozen(out2).spec_sha256 == h1


# --------------------------------------------------------------------------- F1: invisible characters
# Deterministic Unicode policy: a role identifier containing a non-whitespace control (Cc), format
# (Cf: zero-width, bidi marks, soft hyphen, tag characters, U+180E), surrogate (Cs) or one of the
# explicit default-ignorable code points (Hangul fillers, variation selectors, CGJ, ...) is REFUSED,
# never silently stripped. Real whitespace is still collapsed. Homoglyphs are NOT caught.

INVISIBLES = [
    "​",  # zero width space
    "‌",  # ZWNJ
    "‍",  # ZWJ
    "⁠",  # word joiner
    "﻿",  # BOM / ZWNBSP
    "­",  # soft hyphen
    "‎",  # LRM
    "‮",  # RLO
    "⁦",  # LRI
    "\x00",  # NUL
    "\x07",  # BEL
    "\x7f",  # DEL
    "᠎",  # Mongolian vowel separator (Cf)
    "ㅤ",  # Hangul filler
    "ᅟ",  # Hangul choseong filler
    "ᅠ",  # Hangul jungseong filler
    "ﾠ",  # halfwidth Hangul filler
    "️",  # variation selector-16
    "︀",  # variation selector-1
    "\U000e0100",  # variation selector-17
    "͏",  # combining grapheme joiner
    "\U000e0001",  # language tag
    "\U000e0041",  # tag latin capital A
    "឴",  # Khmer inherent vowel Aq
    "᠋",  # Mongolian free variation selector one
    "⠀",  # braille pattern blank
]


def test_lone_surrogate_is_flagged_by_helper():
    # The JSON loader already refuses lone surrogates before this check; the helper still flags one.
    s = Signoff(
        owner="a\ud800b",
        trading_expert="x",
        independent_validator="y",
        date=None,
        spec_sha256=None,
    )
    assert _signoff_invisible_char_roles(s) == [("owner", ("U+D800",))]


@pytest.mark.parametrize("ch", INVISIBLES, ids=lambda c: f"U+{ord(c):04X}")
@pytest.mark.parametrize("position", ["inside", "leading", "trailing", "only"])
def test_invisible_or_control_character_refused_at_freeze(tmp_path, capsys, ch, position):
    value = {
        "inside": f"ali{ch}ce",
        "leading": f"{ch}alice",
        "trailing": f"alice{ch}",
        "only": ch,
    }[position]
    rc, out, err = _try_freeze(tmp_path, capsys, owner=value)
    assert rc == 2 and not out.exists()
    assert "invisible or control" in err and "signoff.owner" in err
    assert f"U+{ord(ch):04X}" in err  # reported by code point, never echoed raw


def test_invisible_character_cannot_split_otherwise_equal_identifiers(tmp_path, capsys):
    # The pre-fix bypass: 'alice' vs 'ali<ZWSP>ce' passed as distinct.
    rc, out, err = _try_freeze(tmp_path, capsys, owner="alice", trading_expert="ali​ce")
    assert rc == 2 and not out.exists() and "trading_expert" in err


def test_real_whitespace_is_still_collapsed_not_refused(tmp_path, capsys):
    for ws in ("\t", "\n", " ", " ", " ", "　", "\u0085"):
        assert _normalize_role_identifier(f"Jay{ws}Wang") == "jay wang"
    rc, out, _ = _try_freeze(tmp_path, capsys, owner="Jay Wang")
    assert rc == 0 and out.exists()


def test_invisible_check_helper_contract():
    s = Signoff(
        owner="ok",
        trading_expert="a​b\x07",
        independent_validator="fine",
        date=None,
        spec_sha256=None,
    )
    assert _signoff_invisible_char_roles(s) == [("trading_expert", ("U+200B", "U+0007"))]


def test_error_type_for_invisible_characters_is_named():
    err = SignoffRoleCharactersError([("owner", ("U+200B",))])
    assert isinstance(err, ValueError) and err.roles == (("owner", ("U+200B",)),)
    assert "owner" in str(err) and "U+200B" in str(err)


def test_load_frozen_reports_invisible_characters_as_unusable(tmp_path, capsys):
    rc, out, _ = _try_freeze(tmp_path, capsys)
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    data["signoff"]["independent_validator"] = "SYNTH-VALI​DATOR"
    out.write_text(json.dumps(data), encoding="utf-8")
    view = load_frozen(out)
    assert view.is_signed is False
    assert any(
        "invisible or control" in r and "independent_validator" in r for r in view.unusable_reasons
    )


def test_homoglyphs_remain_explicitly_not_caught_with_invisible_policy(tmp_path, capsys):
    # Still a known limit: Cyrillic 'a' (U+0430) is visible, not invisible, and not unified.
    rc, out, _ = _try_freeze(tmp_path, capsys, owner="alice", trading_expert="аlice")
    assert rc == 0 and out.exists()


def test_docstrings_and_errors_never_claim_authentication():
    for obj in (
        _normalize_role_identifier,
        _non_distinct_signoff_roles,
        _signoff_invisible_char_roles,
        SignoffRolesNotDistinctError,
        SignoffRoleCharactersError,
    ):
        doc = (obj.__doc__ or "").lower()
        assert "not identity verification" in doc or "unauthenticated" in doc
        assert "authenticates" not in doc.replace("not authenticate", "")
