"""Internal EAD Data-Quality Report (ADR 0037 §4.0).

Built BEFORE any investor-facing opportunity cards: a polished report over incomplete data is
worse than no report. Read-only, off the order path; internal/hidden.
"""

from app.services.data_quality.report import (
    EADDataQualityReport,
    build_govcontract_data_quality,
    render_report,
)

__all__ = ["EADDataQualityReport", "build_govcontract_data_quality", "render_report"]
