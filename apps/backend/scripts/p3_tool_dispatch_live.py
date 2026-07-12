"""P3 live tool-dispatch verification (ADR 0016 / p3-complete).

Drives one agent turn through the real HTTP API and inspects the returned
content blocks for MCP tool dispatch (mcp_tool_use / mcp_tool_result).
Run from a non-Norton, credentialed host with the stack up and the chart-MCP
exposed via a tunnel that AGENT_MCP_SERVER_URL points at.
"""

import json
import sys

import pyotp
import requests

BASE = "http://localhost:8000"
EMAIL = "jay@globalcomplyai.com"
PASSWORD = "WorkbenchDev!2026"
TOTP_SECRET = "HLY7NC3UFQFHPTB3G2EAUP3Y3Y2WQTTO"
PROMPT = (
    "Using your tools, look up my current Alpaca account state and tell me my "
    "cash, equity, and buying power."
)


def main() -> int:
    s = requests.Session()

    code = pyotp.TOTP(TOTP_SECRET).now()
    r = s.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD, "totp_code": code},
        timeout=20,
    )
    print(f"login -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500])
        return 1

    r = s.post(f"{BASE}/api/v1/agent/sessions", json={}, timeout=20)
    print(f"start session -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500])
        return 1
    sid = r.json()["id"]
    model = r.json()["model"]
    print(f"session id={sid} model={model}")

    print("appending message (this runs the agent turn; may take ~30s)...")
    r = s.post(
        f"{BASE}/api/v1/agent/sessions/{sid}/messages",
        json={"text": PROMPT},
        timeout=180,
    )
    print(f"append -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:1000])
        return 1

    r = s.get(f"{BASE}/api/v1/agent/sessions/{sid}", timeout=20)
    detail = r.json()
    print(
        f"session totals: cost=${detail['total_cost_usd']} "
        f"in={detail['total_input_tokens']} out={detail['total_output_tokens']} "
        f"end_reason={detail.get('end_reason')}"
    )

    tool_blocks = []
    print("\n=== conversation content blocks ===")
    for m in detail["messages"]:
        for b in m["content"]:
            btype = b.get("type", "?")
            tag = f"[{m['role']}:{btype}]"
            if "tool" in btype or "mcp" in btype:
                tool_blocks.append((m["role"], btype, b))
                print(f"{tag} {json.dumps(b)[:600]}")
            elif btype == "text":
                print(f"{tag} {b.get('text', '')[:300]}")
            else:
                print(f"{tag} {json.dumps(b)[:300]}")

    print("\n=== VERDICT ===")
    if tool_blocks:
        kinds = sorted({bt for _, bt, _ in tool_blocks})
        print(f"PASS: {len(tool_blocks)} tool block(s) present: {kinds}")
        return 0
    print("FAIL: no tool/mcp blocks found (pure-chat turn).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
