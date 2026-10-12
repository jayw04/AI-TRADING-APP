"""PU-1 Personal-Use Data Presentation Rule: labeling and export controls only.

Leaf package. It must import no order-path module (app.orders / app.risk / app.brokers /
app.services.order_router) and must not be imported by one; ``scripts/check_pu1_presentation_gate.sh``
enforces both directions. Nothing here changes what data is fetched, stored, computed or traded.
"""

from app.licensing.commercial_safe import (
    commercial_ok_source_set,
    commercial_safe_section,
    omission_notice,
)
from app.licensing.envelope import (
    envelope_scope,
    scope_of_file,
    tag_envelope,
    write_sidecar,
)
from app.licensing.gate import (
    REASON_CODE,
    PersonalScopeBlocked,
    assert_presentable,
    effective_scope,
)
from app.licensing.output import (
    export_file_for_external_use,
    export_for_external_use,
    write_internal_report,
)
from app.licensing.registry import (
    LicenseRegistryError,
    alpaca_feed_source_id,
    load_registry,
)
from app.licensing.render import PERSONAL_FOOTER, footer_for, stamp
from app.licensing.scopes import LicenseScope, Scoped, combine_scopes, derive

__all__ = [
    "PERSONAL_FOOTER",
    "REASON_CODE",
    "LicenseRegistryError",
    "LicenseScope",
    "PersonalScopeBlocked",
    "Scoped",
    "alpaca_feed_source_id",
    "assert_presentable",
    "combine_scopes",
    "commercial_ok_source_set",
    "commercial_safe_section",
    "derive",
    "effective_scope",
    "envelope_scope",
    "export_file_for_external_use",
    "export_for_external_use",
    "footer_for",
    "load_registry",
    "omission_notice",
    "scope_of_file",
    "stamp",
    "tag_envelope",
    "write_internal_report",
    "write_sidecar",
]
