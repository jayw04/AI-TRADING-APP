"""Alternative-data subsystem (ADR 0027).

Read-only, off-the-order-path ingestion of *non-price* information classes — the first
being corporate events from SEC filings (``app.altdata.sec``), persisted into a
point-in-time Event Store (``app.altdata.events``). Nothing here imports the OrderRouter,
risk engine, or brokers; events flow Source -> store -> research -> governance -> execution,
never directly to the order path.
"""
