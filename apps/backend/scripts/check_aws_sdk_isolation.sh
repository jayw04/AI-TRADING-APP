#!/bin/bash
# check_aws_sdk_isolation.sh
#
# CI invariant #18: the AWS SDK is reachable from exactly one package.
#
# ADR 0046 introduced boto3 as a direct dependency so the forward-validation
# witness can sign in AWS KMS. The property that makes that safe is NOT that
# the SDK is absent from the image — it is present, and any deployment could
# install it anyway. The property is that no code outside
# app/validation/aws/ can reach AWS at all.
#
# Architecture: this is an ALLOWLIST, not a denylist, exactly like
# check_no_llm_in_order_path.sh (ADR 0006 v2). Every module is presumed
# forbidden from importing the SDK unless it appears in ALLOWED_DIRS. A
# denylist over enumerated paths would silently permit a new file added
# somewhere nobody listed — which is the one PR nobody looks closely at.
#
# Two directions are enforced:
#
#   1. OUTBOUND — nothing outside the allowlist imports the AWS SDK.
#   2. INBOUND  — nothing outside the allowlist imports app.validation.aws.
#      The adapters are reached ONLY through the witness.signer.factory /
#      witness.sink.factory strings in the governed deployment configuration,
#      resolved by witness_enforcement._resolve_factory. A static import
#      anywhere else would create a code path to AWS that the governed
#      configuration does not control.
#
# Type-only imports count. types_boto3*/mypy_boto3* stub packages are an
# ungoverned dependency path just as much as boto3 itself, and "it is only for
# typing" is how the boundary erodes. Matching is indentation-insensitive so an
# import inside `if TYPE_CHECKING:` or inside a function is caught too.
#
# Weakening or removing this invariant requires a successor ADR.

set -e

APP_ROOT="apps/backend/app"
TEST_ROOT="apps/backend/tests"

# Any AWS SDK distribution, including the typing stubs.
SDK_IMPORT_RE='^[[:space:]]*(import|from)[[:space:]]+(boto3|botocore|aiobotocore|types_boto3[A-Za-z0-9_]*|mypy_boto3[A-Za-z0-9_]*)([.[:space:]]|$)'

# The adapter package itself, referenced as a module path.
ADAPTER_IMPORT_RE='^[[:space:]]*(import|from)[[:space:]]+app\.validation\.aws([.[:space:]]|$)'

# Production code permitted to import the AWS SDK.
# IMPORTANT: keep this MINIMAL. Adding to it requires an ADR.
ALLOWED_DIRS=(
    "${APP_ROOT}/validation/aws"             # ADR 0046: KMS witness signer (4A) + S3 Object-Lock sink (4B)
)

# Tests permitted to import the AWS SDK or the adapter package: the signer and
# sink tests, and nothing else.
ALLOWED_TEST_DIRS=(
    "${TEST_ROOT}/validation/aws"            # ADR 0046: Stubber-based adapter tests
)

build_prune_args() {
    PRUNE_ARGS=()
    for allowed in "$@"; do
        PRUNE_ARGS+=(-not -path "${allowed}*")
    done
}

scan() {
    # scan <root> <regex> <allowed dirs...>
    local root="$1" regex="$2"
    shift 2
    [ -d "$root" ] || return 0
    build_prune_args "$@"
    find "$root" -name "*.py" "${PRUNE_ARGS[@]}" \
        -exec grep -HnE "$regex" {} \; 2>/dev/null || true
}

VIOLATIONS=""

# 1. OUTBOUND — SDK imports outside the allowlist.
FOUND=$(scan "$APP_ROOT" "$SDK_IMPORT_RE" "${ALLOWED_DIRS[@]}")
[ -n "$FOUND" ] && VIOLATIONS+="AWS SDK imported in non-allowlisted production code:"$'\n'"$FOUND"$'\n\n'

FOUND=$(scan "$TEST_ROOT" "$SDK_IMPORT_RE" "${ALLOWED_TEST_DIRS[@]}")
[ -n "$FOUND" ] && VIOLATIONS+="AWS SDK imported in non-allowlisted tests:"$'\n'"$FOUND"$'\n\n'

# 2. INBOUND — static imports of the adapter package outside the allowlist.
FOUND=$(scan "$APP_ROOT" "$ADAPTER_IMPORT_RE" "${ALLOWED_DIRS[@]}")
[ -n "$FOUND" ] && VIOLATIONS+="app.validation.aws imported outside the adapter package:"$'\n'"$FOUND"$'\n\n'

FOUND=$(scan "$TEST_ROOT" "$ADAPTER_IMPORT_RE" "${ALLOWED_TEST_DIRS[@]}")
[ -n "$FOUND" ] && VIOLATIONS+="app.validation.aws imported outside the adapter tests:"$'\n'"$FOUND"$'\n\n'

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: AWS SDK isolation violated (ADR 0046)."
    echo ""
    echo "$VIOLATIONS"
    echo "The AWS SDK is reachable from app/validation/aws/ only, and that package is"
    echo "reached only through the witness.signer.factory / witness.sink.factory strings"
    echo "in the governed deployment configuration. See:"
    echo "  docs/adr/0046-aws-kms-witness-signer-boundary.md"
    echo ""
    echo "If a new module genuinely needs AWS access, that is an architectural change:"
    echo "  1. Confirm it cannot be reached through the existing witness factory seam."
    echo "  2. Write the ADR that authorizes the new boundary."
    echo "  3. Only then add the path to ALLOWED_DIRS in this script."
    echo ""
    echo "Importing the SDK 'only for type hints' is not an exception — a stub package"
    echo "is an ungoverned dependency path just as much as the runtime one."
    exit 1
fi

echo "AWS SDK isolation invariant OK"
exit 0
