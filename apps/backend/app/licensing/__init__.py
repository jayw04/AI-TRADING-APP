"""PU-1 Personal-Use Data Presentation Rule: labeling and export controls only.

Leaf package. It must import no order-path module (app.orders / app.risk / app.brokers /
app.services.order_router) and must not be imported by one; ``scripts/check_pu1_presentation_gate.sh``
enforces both directions. Nothing here changes what data is fetched, stored, computed or traded.
"""

from app.licensing.broker_fields import (
    FieldClass,
    classify_field,
    field_license_block,
    scope_of_fields,
    sources_of_fields,
    subset_with_lineage,
    taint_from_fields,
)
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
    write_internal_json,
    write_internal_report,
)
from app.licensing.registry import (
    ALPACA_MARKET_DATA,
    OWNER_GENERATED_RECORDS,
    LicenseRegistryError,
    alpaca_feed_source_id,
    load_registry,
)
from app.licensing.render import PERMISSION_NOTE, PERSONAL_FOOTER, footer_for, stamp
from app.licensing.scopes import LicenseScope, Scoped, combine_scopes, derive

__all__ = [
    "ALPACA_MARKET_DATA",
    "OWNER_GENERATED_RECORDS",
    "PERMISSION_NOTE",
    "PERSONAL_FOOTER",
    "REASON_CODE",
    "FieldClass",
    "LicenseRegistryError",
    "LicenseScope",
    "PersonalScopeBlocked",
    "Scoped",
    "alpaca_feed_source_id",
    "assert_presentable",
    "classify_field",
    "combine_scopes",
    "commercial_ok_source_set",
    "commercial_safe_section",
    "derive",
    "effective_scope",
    "envelope_scope",
    "export_file_for_external_use",
    "export_for_external_use",
    "field_license_block",
    "footer_for",
    "load_registry",
    "omission_notice",
    "scope_of_fields",
    "scope_of_file",
    "sources_of_fields",
    "stamp",
    "subset_with_lineage",
    "tag_envelope",
    "taint_from_fields",
    "write_internal_json",
    "write_internal_report",
    "write_sidecar",
]
