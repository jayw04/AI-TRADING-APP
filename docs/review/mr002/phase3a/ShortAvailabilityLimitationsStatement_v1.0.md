# MR-002 Phase 3A — Short Availability & Locate Limitations Statement

**Scope:** discloses the limits of the short-side realism model. Phase 3A drafting only; opens no data.

## Governing distinction

- The **preregistered net model** (PRIMARY_GATE) includes **borrow financing cost** (50 bps/yr; 300 bps/yr stress) and **assumes borrow availability**. `net_oos_sharpe >= 0.70` is computed on this series and is **not** moved to the conservative view.
- The **conservative availability/locate/SSR model** (SECONDARY / ECONOMIC_OPERABILITY_GATE) adds availability, locate-failure, and Reg SHO/SSR realism. It **may block product promotion** but does **not** replace the frozen primary statistical test.
- **Zero-borrow-cost frictionless attribution** is `DIAGNOSTIC_ONLY` (`FRICTIONLESS_SHORT_RESEARCH_DIAGNOSTIC / NOT AN IMPLEMENTABLE PERFORMANCE ESTIMATE`).

## Unobservable facts (not manufactured)

PIT borrow **availability / locate** is generally not reconstructable at this data tier. It is labeled `UNOBSERVABLE_LIMITATION` and handled by a **conservative proxy** (shortable only above a preregistered liquidity/size floor at close t; otherwise `REFUSED_SHORT_UNAVAILABLE`), never by synthetic locate data. Reg SHO/SSR is applied where reconstructable from PIT price and otherwise disclosed as a limitation.

## Governed answers (frozen before validation)

- Short cannot be located -> **refused** (fail-closed), never synthetically located or silently resized.
- A refused short **never** creates a naked long or ghost position; the paired long gross is reduced under a preregistered reconstruction rule to preserve dollar-neutrality.
- Buy-to-cover failure -> fail-closed `INTEGRITY_STOP`; pending exits are executed at next-open t+1, never dropped.

The exact conservative-view floor and reconstruction rule are frozen in `ShortBorrowLocateModelSpecification_v1.0.json` before validation opens.
