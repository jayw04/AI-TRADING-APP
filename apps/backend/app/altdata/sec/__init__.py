"""SEC Filing Capability (ADR 0027) — the first implementation of the broader Corporate
Event Capability.

Layered: ``Corporate Event Capability -> SEC Filing Capability -> Form 4`` (this module's
initial filing type). Read-only EDGAR access:

- ``client.EdgarClient`` — a fair-access-compliant (User-Agent + rate limit) read-only HTTP client.
- ``cik_map`` — ticker <-> CIK resolution from EDGAR's ``company_tickers.json``.
- ``form4`` — parse a Form 4 ``ownershipDocument`` XML into structured insider transactions.
- ``ingest`` — orchestrate: submissions -> Form 4 docs -> parse -> the PIT Event Store.

Off the order path; public source, no credential (just a declared User-Agent).
"""
