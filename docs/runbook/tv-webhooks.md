# TradingView Pine Webhook Setup

The workbench accepts Pine alert webhooks from TradingView. Each accepted
alert becomes a `Signal` row with `type='pine_alert'` and publishes on the
event bus as `signal.new`.

> **UI surfacing.** A dedicated Signals view lands in P2 Session 5. Until
> then, verify alerts via `GET /api/v1/signals` (P2 S4) once that endpoint
> lands, the backend log line `tv_alert_accepted`, or a direct SQLite
> query against the `signals` table.

## One-time setup

### 1. Generate your webhook secret

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users/me/regenerate-webhook-secret
```

Response includes a 256-bit URL-safe secret. **Save it now.** The GET
endpoint (`/api/v1/users/me/webhook-secret`) will show it again, but
rotation invalidates the old one immediately — every TV alert that
references the old secret must be updated.

### 2. Expose your backend to the internet

TradingView's webhook senders are on TV's infrastructure, not your local
machine. You need a public URL that routes to `http://127.0.0.1:8000`.

Recommended: Cloudflare Tunnel.

```bash
cloudflared tunnel create workbench-alerts
cloudflared tunnel route dns workbench-alerts workbench-alerts.<your-domain>
# In ~/.cloudflared/config.yml under ingress:
#   - hostname: workbench-alerts.<your-domain>
#     service: http://localhost:8000
cloudflared tunnel run workbench-alerts
```

Confirm reachability:

```bash
curl -X POST https://workbench-alerts.<your-domain>/api/v1/alerts/tv \
  -H "Content-Type: application/json" \
  -d '{"secret":"<your-secret>","symbol":"AAPL"}'
# Expect 200 with a signal_id.
```

> **Local-only.** You can skip the tunnel and test against
> `http://127.0.0.1:8000` directly via curl (step 4 below). Only the TV
> side needs the public URL.

### 3. Configure the TV alert

On any TradingView chart:

1. Right-click → Add alert.
2. Set the condition (any Pine alert condition or built-in indicator alert).
3. **Notifications tab → Webhook URL:**
   `https://workbench-alerts.<your-domain>/api/v1/alerts/tv`
4. **Message:** paste the JSON template below. TradingView substitutes
   `{{ticker}}`, `{{close}}`, etc. at alert time.

```json
{
  "secret": "<paste-your-secret-here>",
  "symbol": "{{ticker}}",
  "side": "buy",
  "payload": {
    "price": "{{close}}",
    "alert_name": "{{plot_title}}",
    "interval": "{{interval}}",
    "comment": "{{strategy.order.comment}}"
  }
}
```

For an exit alert, use `"side": "sell"`. For a non-directional info alert
(e.g. "RSI crossed 50"), omit `side`.

### 4. (Optional) Bind to a strategy

If you have a Python strategy you want to feed signals into, add
`"strategy_id": <id>` to the JSON body. The backend verifies the strategy
belongs to you (the secret identifies the user).

```json
{
  "secret": "<your-secret>",
  "symbol": "{{ticker}}",
  "strategy_id": 5,
  "side": "buy"
}
```

> **Strategy `on_signal` dispatch is P2 Session 5/6.** Until then, the
> signal row is persisted and bus-published but no strategy handler fires.

### 5. Verify

After saving the alert, force-fire it from TV's alert manager (Manage
Alerts → ⋮ → Test).

Backend log line:

```bash
docker compose logs backend | grep tv_alert_accepted
```

Direct DB query:

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT id, symbol_id, type, json_extract(payload_json, '\$.alert_name') AS name
   FROM signals WHERE type='pine_alert' ORDER BY id DESC LIMIT 5;"
```

The signal also broadcasts on the event bus as `signal.new`. Once the
Signals UI lands (P2 S5) it will update live via WS.

## Limits

- **Dedup window: 5 seconds.** Identical alerts (same user × symbol ×
  side × strategy_id × payload) within 5s produce one signal row.
- **Rate limit: 20 alerts per minute per secret.** The 21st returns 429
  and is dropped.
- **Failed-auth IP throttle: 10 bad-secret POSTs per minute per IP.** The
  11th from the same IP returns 429. Successful posts do NOT count toward
  this budget.
- **Symbol must be known** to the workbench (in `symbols` table). For
  US equities pulled by Alpaca this is automatic; for international or
  exotic instruments, populate `symbols` manually first.

## Failure modes

- **TV's webhook delivery is best-effort.** If the backend is down when
  TV fires, the alert is lost. There is no retry. Design strategies that
  can tolerate missed alerts.
- **The secret sits in the alert body in plaintext.** Don't share alert
  exports without redacting it. If a secret leaks, rotate immediately.
- **In-memory dedup and rate limit.** A backend restart clears both. A
  multi-worker future (P5) would need a shared store — fix when it
  becomes real.

## Rotation

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users/me/regenerate-webhook-secret
```

Update every TV alert that uses the old secret. The old secret stops
working immediately.

## Troubleshooting

Check the backend `tv_alert_*` log lines:

- `tv_alert_bad_secret` → wrong secret in body
- `tv_alert_unknown_symbol` → ticker not in the `symbols` table
- `tv_alert_user_rate_limited` → over 20/min for this secret
- `tv_alert_ip_rate_limited` → over 10 failed-auth/min from this IP
- `tv_alert_strategy_ownership_mismatch` → `strategy_id` belongs to a
  different user
- `tv_alert_deduped` → identical alert in the last 5s
- `tv_alert_accepted` → row written, bus event published

If you see nothing at all: the request didn't reach the backend. Check
your tunnel, the URL, and TV's own log (Manage Alerts → Logs).
