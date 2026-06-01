"""P5 §8.4 — the structlog redaction processor scrubs every credential pattern
family from §4 before logs reach stdout."""

from app.observability.redact import _redact_value, redact_processor


def test_redacts_fernet_token():
    msg = f"key=gAAAAABh{'x' * 60} trailing"
    out = _redact_value(msg)
    assert "gAAAAABh" not in out
    assert "[REDACTED:fernet]" in out


def test_redacts_anthropic_key():
    key = "sk-ant-1234567890abcdefghij"
    out = _redact_value(f"api_key={key}")
    assert key not in out
    assert "[REDACTED:anthropic]" in out


def test_redacts_alpaca_live():
    key = "PKLIVE1234567890ABCD"
    out = _redact_value(f"Authorization: {key}")
    assert key not in out
    assert "[REDACTED:alpaca_live]" in out


def test_redacts_alpaca_paper():
    key = "PKTEST1234567890ABCD"
    out = _redact_value(f"key={key}")
    assert key not in out
    assert "[REDACTED:alpaca_paper]" in out


def test_redacts_generic_assignment():
    out = _redact_value("secret=mySuperSecretValue12345")
    assert "mySuperSecretValue12345" not in out
    assert "[REDACTED:generic]" in out


def test_redacts_nested_dict():
    event = {"msg": "hi", "details": {"api_key": "sk-ant-thisShouldNotAppear12345"}}
    out = _redact_value(event)
    assert "thisShouldNotAppear12345" not in str(out)


def test_processor_redacts_event_dict():
    out = redact_processor(None, None, {"msg": "creds: sk-ant-1234567890abcdefghij"})
    assert "sk-ant-1234567890abcdefghij" not in str(out)


def test_processor_passes_through_non_strings():
    out = redact_processor(None, None, {"count": 42, "ok": True, "items": [1, 2, 3]})
    assert out["count"] == 42
    assert out["ok"] is True
    assert out["items"] == [1, 2, 3]
