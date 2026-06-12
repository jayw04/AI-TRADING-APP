"""Definitive verification for ADR 0017 (OS trust store for outbound TLS).

Proves the fix the only way that's meaningful: with a TLS-inspecting proxy
(Norton) ACTIVELY MITM'ing. It:

  1. Reads the cert issuer data.alpaca.markets presents. If it's the real
     Alpaca issuer (Let's Encrypt / DigiCert), the inspector is OFF and the
     test is inconclusive — it says so and stops.
  2. If a Norton/Symantec-signed cert is served (inspector ON), it runs the
     two paths in clean subprocesses:
       - certifi-only (the pre-fix behavior)  -> expected to FAIL
       - OS trust store via truststore (the fix) -> expected to PASS
     and exercises the real PR code path (_alpaca_fetch_bars).

    cd apps/backend
    .venv/Scripts/python.exe scripts/verify_tls_trust.py
"""

from __future__ import annotations

import socket
import ssl
import subprocess
import sys

HOST = "data.alpaca.markets"
URL = f"https://{HOST}/v2/stocks/AAPL/bars?timeframe=1Day&limit=1"


def served_issuer() -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((HOST, 443), timeout=15) as s:
        with ctx.wrap_socket(s, server_hostname=HOST) as ss:
            der = ss.getpeercert(binary_form=True)
    from cryptography import x509

    return x509.load_der_x509_certificate(der).issuer.rfc4514_string()


# Tiny one-liner probes run in fresh interpreters so truststore is/ isn't active.
_CERTIFI = (
    "import requests,sys\n"
    "try:\n"
    f"    r=requests.get({URL!r},headers={{'APCA-API-KEY-ID':'x','APCA-API-SECRET-KEY':'x'}},timeout=15)\n"
    "    print('PASS',r.status_code)\n"
    "except Exception as e:\n"
    "    print('FAIL',type(e).__name__,str(e)[:90]); sys.exit(1)\n"
)
_TRUSTSTORE = "import truststore;truststore.inject_into_ssl()\n" + _CERTIFI


def run_probe(label: str, code: str) -> bool:
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip().splitlines()
    print(f"  {label:<28} -> {out[-1] if out else '(no output)'}")
    return p.returncode == 0


def main() -> int:
    print(f"Probing cert {HOST} presents ...")
    issuer = served_issuer()
    norton = any(k in issuer.lower() for k in ("norton", "symantec", "broadcom"))
    print(f"  issuer: {issuer}")
    print(f"  Norton SSL inspection ACTIVE -> {norton}\n")

    if not norton:
        print("INCONCLUSIVE: the inspector is OFF (real Alpaca cert served).")
        print("Turn ON Norton's 'encrypted-connection / SSL scanning', then re-run.")
        print("(Norton > Settings > Firewall/Safe Web > Encrypted Connections Scanning,")
        print(" or Settings > Antivirus > Scans and Risks - name varies by version.)")
        return 2

    print("Inspector ACTIVE — running the decisive comparison:")
    certifi_ok = run_probe("certifi-only (pre-fix)", _CERTIFI)
    truststore_ok = run_probe("OS trust store (the fix)", _TRUSTSTORE)

    print("\nReal PR code path (_alpaca_fetch_bars, which injects truststore):")
    try:
        from datetime import UTC, datetime

        from app.market_data.bar_cache import _alpaca_fetch_bars

        df = _alpaca_fetch_bars(
            "AAPL", "1Day", datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 11, tzinfo=UTC)
        )
        print(f"  _alpaca_fetch_bars -> PASS ({len(df)} bars)")
        fetch_ok = len(df) > 0
    except Exception as e:  # noqa: BLE001
        print(f"  _alpaca_fetch_bars -> FAIL {type(e).__name__}: {str(e)[:90]}")
        fetch_ok = False

    print("\n=== VERDICT ===")
    if (not certifi_ok) and truststore_ok and fetch_ok:
        print("CONFIRMED: certifi FAILS under inspection, OS trust store PASSES, and the")
        print("PR code path fetches real bars with Norton ON. ADR 0017 fix verified.")
        return 0
    if certifi_ok:
        print("UNEXPECTED: certifi passed under inspection — Norton may not be MITM'ing")
        print("this host/port, or a custom CA bundle is in play. Re-check the issuer above.")
        return 1
    print("FAIL: OS-trust path did not pass — investigate truststore install / injection.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
