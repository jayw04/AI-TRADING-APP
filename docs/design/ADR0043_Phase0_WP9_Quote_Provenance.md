# WP9 — Market-Data Provenance as First-Class Evidence (AMD-19)

| Field | Value |
|-------|-------|
| Package | WP9 (AMD-19; Section 8.1 Quote category; dataset-gate blocking) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **COMPLETE** (offline quote provenance schema; broker HOLD) |
| Depends on | WP2 tiers; WP7 evidence bundles |
| Broker submission | **HOLD** |
| Created | 2026-07-29 |

## Goal

Quote-source semantics must be **structured evidence**, not a free-text string.
“IEX displayed spread” was central to the Phase-0 defect; provenance fields are
mandatory before a quote may enter an evidence package or dataset gate.

## Required quote schema fields (AMD-19)

| Field | Purpose |
|-------|---------|
| `provider` | e.g. `alpaca` |
| `feed_type` | e.g. `iex`, `sip`, `otc` |
| `venue_scope` | `venue` or `consolidated` |
| `subscription_entitlement` | what the operator was entitled to receive |
| `condition_codes` | exchange/condition codes when present |
| `sequence_number` | when available |
| `raw_payload_hash` | SHA-256 of the raw payload bytes |
| `normalization_version` | schema/normalizer pin |

Missing required fields → **refuse** (not silently defaulted to a string label).

## Remaining gates (documented, not wired live)

Offline packages for WP0–WP9 now cover the controlling-design sequence through
provenance. Live dataset unseal (AMD-08), shadow grading (AMD-04), and Option A/C
threshold harnesses (AMD-10) remain **HOLD** with broker submission until
deployed through governance.

## In scope

- `phase0_quote_provenance.py` — schema, validate, hash, evidence envelope
- Hermetic tests (string-only refuse; complete schema accept; hash stability)
- This package doc + controlling-design WP9 row freeze

## Out of scope

- Live Alpaca quote-path rewrite
- Dataset unseal scripts
- Broker submission / formal canary (HOLD)

## Exit criteria

- [x] Package doc
- [x] Structured schema with all AMD-19 fields
- [x] String-only “IEX displayed spread” → refuse
- [x] Raw payload hash + normalization version required
- [x] No order-path imports
- [x] HOLD unchanged
- [x] Controlling-design sequence marks WP0–WP9 offline packages complete

## Deliverables

1. This document.
2. `apps/backend/app/risk/loss_control/phase0_quote_provenance.py`
3. `apps/backend/tests/risk/test_phase0_quote_provenance.py`
