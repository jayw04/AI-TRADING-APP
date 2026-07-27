#!/usr/bin/env bash
#
# Step 4D — provision the production witness boundary (ADR 0047).
#
# OPERATOR-RUN, never run by the instance role. The runner holds neither kms:CreateKey nor
# s3:CreateBucket and must not: a role able to create the resources whose properties it attests could
# also weaken them. Everything here is therefore executed by an administrator, and every resource
# identity is written to the journal as it is created — the same split that let Step 4C mark its
# resources OPERATOR_PROVISIONED.
#
# ⚠⚠ STEP 2 IS IRREVERSIBLE. The bucket is created with Object Lock and a COMPLIANCE default retention
# of 2555 days. Under COMPLIANCE, retention cannot be shortened or bypassed by ANYONE, including the
# account root. Nothing written to the bucket can be deleted for seven years, and the bucket itself
# cannot be removed while it holds a locked object. This is ADR 0047 Decision (2), ratified, not a
# default this script chose.
#
# Usage:
#   deploy/aws/provision-step4d-witness.sh --plan     # print what would be created, touch nothing
#   deploy/aws/provision-step4d-witness.sh --apply    # create it, after an explicit typed confirmation
#
set -euo pipefail

REGION="us-east-1"
ACCOUNT="219024422756"
BUCKET="workbench-witness-forward-validation-${ACCOUNT}"
ROLE="workbench-forward-validation-witness"
POLICY_NAME="WitnessBoundary"
HOST_NAME="ec2-forward-validation"
INSTANCE_TYPE="t3.small"

# ADR 0047 (2). Named as constants so a diff of this file shows a change to the ratified policy.
RETENTION_MODE="COMPLIANCE"
RETENTION_DAYS=2555

# ADR 0047 (3).
OPERATIONAL_PREFIX="witness"
PREFLIGHT_PREFIX="preflight"

JOURNAL="${JOURNAL:-step4d_operator_provisioning.json}"

MODE="${1:---plan}"

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# `"$@"`, not `"$1"`: every caller passes --arg/--argjson pairs BEFORE the filter, so taking only the
# first argument fed jq a bare `--argjson` with nothing after it. That broke the first live run,
# immediately after the KMS key was created and before the bucket — and `--plan` could not have caught
# it, because `--plan` never wrote a journal. Defined up here, beside the other helpers, so the plan
# rehearsal below can exercise it; a rehearsal that skips the code paths `--apply` uses rehearses the
# wrong thing.
journal() { jq "$@" "$JOURNAL" > "$JOURNAL.tmp" && mv "$JOURNAL.tmp" "$JOURNAL"; }

# ── preconditions ────────────────────────────────────────────────────────────────────────────────────

command -v aws >/dev/null || die "aws CLI not found"
command -v jq  >/dev/null || die "jq not found"

CALLER="$(aws sts get-caller-identity --output json)"
CALLER_ACCOUNT="$(echo "$CALLER" | jq -r .Account)"
[ "$CALLER_ACCOUNT" = "$ACCOUNT" ] || die "caller is in account $CALLER_ACCOUNT, expected $ACCOUNT"

KEY_DESCRIPTION="Trading Workbench forward-validation witness signer (ADR 0047)"

# ── the governed parameters, rendered once ───────────────────────────────────────────────────────────
#
# Both the policy that gets installed and the point-of-no-return echo come from these two functions, and
# `--plan` calls them too. That last part is deliberate: the echo is a `jq` program that runs at the one
# moment in this script where a failure is least acceptable, and `--plan` is where it gets exercised —
# on the host that will run it, against the same jq build, before anything irreversible has happened.
# An untested expression guarding an irreversible step is not a guard.

witness_policy() {   # $1 = key ARN
  cat <<POLICY
{ "Version": "2012-10-17", "Statement": [
  { "Sid": "SignWithTheOneKey", "Effect": "Allow",
    "Action": ["kms:GetPublicKey", "kms:Sign"],
    "Resource": "$1" },
  { "Sid": "ProveTheBucketIsWriteOnce", "Effect": "Allow",
    "Action": ["s3:GetBucketLocation", "s3:GetBucketVersioning",
               "s3:GetBucketObjectLockConfiguration"],
    "Resource": "arn:aws:s3:::$BUCKET" },
  { "Sid": "ListOnlyTheGovernedPrefixes", "Effect": "Allow",
    "Action": "s3:ListBucket",
    "Resource": "arn:aws:s3:::$BUCKET",
    "Condition": { "StringLike": { "s3:prefix": ["$OPERATIONAL_PREFIX/*", "$PREFLIGHT_PREFIX/*"] } } },
  { "Sid": "WriteAndReadTheGovernedPrefixes", "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject"],
    "Resource": ["arn:aws:s3:::$BUCKET/$OPERATIONAL_PREFIX/*",
                 "arn:aws:s3:::$BUCKET/$PREFLIGHT_PREFIX/*"] }
] }
POLICY
}

# The eight actions are EXTRACTED from the policy that will actually be installed, never restated.
# A restatement is a second source of truth, and this is the one place that must not have one.
parameter_echo() {   # $1 = key ARN
  jq -n \
    --arg account "$ACCOUNT" --arg region "$REGION" --arg bucket "$BUCKET" \
    --arg key_arn "$1" --arg key_desc "$KEY_DESCRIPTION" \
    --arg mode "$RETENTION_MODE" --argjson days "$RETENTION_DAYS" \
    --arg op "$OPERATIONAL_PREFIX" --arg pf "$PREFLIGHT_PREFIX" \
    --arg itype "$INSTANCE_TYPE" --arg host "$HOST_NAME" --arg role "$ROLE" \
    --argjson policy "$(witness_policy "$1")" \
    '{
       adr: "0047",
       aws_account: $account,
       region: $region,
       bucket: $bucket,
       kms: { key_arn: $key_arn, description: $key_desc,
              tags: [{TagKey: "workbench-purpose", TagValue: "forward-validation-witness"},
                     {TagKey: "workbench-production", TagValue: "true"}],
              key_spec: "ECC_NIST_P256", key_usage: "SIGN_VERIFY", alias: null },
       object_lock: { mode: $mode, days: $days, irreversible: true },
       prefixes: { operational: ($op + "/"), preflight: ($pf + "/") },
       host: { name: $host, instance_type: $itype, role: $role },
       witness_policy: $policy,
       witness_actions: ($policy.Statement | map(.Action) | flatten | sort)
     }'
}

cat <<PLAN
Step 4D production witness boundary — ADR 0047

  account          $ACCOUNT   ($(echo "$CALLER" | jq -r .Arn))
  region           $REGION
  KMS key          ECC_NIST_P256 / SIGN_VERIFY, NO ALIAS
  bucket           $BUCKET
                   versioning=Enabled, ObjectLock=Enabled at creation
                   DefaultRetention = $RETENTION_MODE / $RETENTION_DAYS days   <-- IRREVERSIBLE
  prefixes         $OPERATIONAL_PREFIX/   (operational, stays empty until the first observation)
                   $PREFLIGHT_PREFIX/  (synthetic preflight evidence only)
  role             $ROLE  (+ instance profile, inline policy $POLICY_NAME)
                   kms:GetPublicKey kms:Sign
                   s3:GetBucketLocation s3:GetBucketVersioning s3:GetBucketObjectLockConfiguration
                   s3:ListBucket s3:PutObject s3:GetObject
                   + AmazonSSMManagedInstanceCore, attached SEPARATELY (host management)
  host             $HOST_NAME  $INSTANCE_TYPE, Amazon Linux, SSM-managed, no inbound
  journal          $JOURNAL

PLAN

if [ "$MODE" = "--plan" ]; then
  # Render the point-of-no-return echo now, with a placeholder ARN, so the jq program that guards the
  # irreversible step is proven on this host before --apply can reach it.
  echo "── the point-of-no-return echo, rehearsed (key ARN is a placeholder) ──────────"
  PLAN_ECHO="$(parameter_echo "arn:aws:kms:$REGION:$ACCOUNT:key/NOT-YET-CREATED")" \
    || die "the parameter echo failed to render; fix that before --apply, because it guards the "\
"irreversible step"
  echo "$PLAN_ECHO"
  PLAN_ACTIONS="$(echo "$PLAN_ECHO" | jq '.witness_actions | length')"
  [ "$PLAN_ACTIONS" = "8" ] || die "the witness policy grants $PLAN_ACTIONS actions, not the ratified 8"

  # Rehearse a journal write against a throwaway file, with the same --argjson shape --apply uses.
  # This is the check that would have caught the `journal "$1"` defect before it reached live AWS.
  # Deliberately beside the real journal rather than in $TMPDIR: on Git Bash `mktemp` returns an MSYS
  # path (/tmp/...) that a native-Windows jq cannot open, so a $TMPDIR rehearsal would fail on the
  # operator's machine for a reason that has nothing to do with what it is testing. The real journal is
  # CWD-relative too, so this exercises the same path shape --apply uses.
  PLAN_JOURNAL="./.step4d_plan_journal.$$.json"
  echo '{}' > "$PLAN_JOURNAL"
  ( JOURNAL="$PLAN_JOURNAL"; journal --argjson e "$PLAN_ECHO" '.parameter_echo = $e' ) \
    || { rm -f "$PLAN_JOURNAL"; die "the journal writer failed; --apply would break mid-provisioning"; }
  jq -e '.parameter_echo.witness_actions | length == 8' "$PLAN_JOURNAL" >/dev/null \
    || { rm -f "$PLAN_JOURNAL"; die "the journal writer did not record the parameter echo"; }
  rm -f "$PLAN_JOURNAL" "$PLAN_JOURNAL.tmp"
  echo
  log "plan only; nothing was created (witness_actions=$PLAN_ACTIONS, journal writer OK)"
  exit 0
fi
[ "$MODE" = "--apply" ] || die "usage: $0 [--plan|--apply]"

# The confirmation is typed, not a y/n. A seven-year irreversible commitment should not be one keystroke
# away from an operator who meant to press enter on something else.
echo "Type exactly:  I ACCEPT $RETENTION_MODE $RETENTION_DAYS DAYS"
read -r CONFIRM
[ "$CONFIRM" = "I ACCEPT $RETENTION_MODE $RETENTION_DAYS DAYS" ] || die "not confirmed; nothing created"

aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null && \
  die "bucket $BUCKET already exists — refusing to re-provision over an existing witness"

echo '{}' | jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{step:"4D", phase:"operator-provisioning", provisioned_by:"OPERATOR", started_at:$t}' > "$JOURNAL"


# ── 1. the signing key ───────────────────────────────────────────────────────────────────────────────

log "creating the KMS signing key"
KEY_JSON="$(aws kms create-key \
  --region "$REGION" \
  --key-spec ECC_NIST_P256 \
  --key-usage SIGN_VERIFY \
  --description "$KEY_DESCRIPTION" \
  --tags TagKey=workbench-purpose,TagValue=forward-validation-witness \
         TagKey=workbench-production,TagValue=true \
  --output json)"
KEY_ARN="$(echo "$KEY_JSON" | jq -r .KeyMetadata.Arn)"
log "key $KEY_ARN"
journal --argjson k "$KEY_JSON" '.kms = $k.KeyMetadata'

# Deliberately NO alias. ADR 0047 (1): an alias can be repointed at a different key without the governed
# configuration changing, and the gate refuses aliases anyway — creating none removes the temptation.

WITNESS_POLICY="$(witness_policy "$KEY_ARN")"

# ── 1b. POINT OF NO RETURN — machine-readable parameter echo ─────────────────────────────────────────
#
# Everything up to here is reversible: a KMS key can be scheduled for deletion. The next command is not.
# `create-bucket --object-lock-enabled-for-bucket` followed by a COMPLIANCE default retention commits
# every object ever written to it, and the bucket itself, for the full period with no remedy available
# to anyone including the account root.
#
# So the last thing before it is a machine-readable echo of every governed parameter, emitted as JSON
# rather than as prose: an operator confirming a formatted paragraph is confirming that it reads
# plausibly, while a JSON object can be diffed against the ADR, captured, and archived alongside the
# evidence. The eight actions are extracted FROM the policy document that will actually be installed,
# not restated — a restatement is a second source of truth and this is the one place that must not have
# one.

ECHO_FILE="${ECHO_FILE:-step4d_parameter_echo.json}"
PARAMETER_ECHO="$(parameter_echo "$KEY_ARN")"

# The tags are asserted against what KMS actually recorded, not against what was requested: the echo
# claims the key is tagged, and a claim the operator is about to confirm should be read back.
aws kms list-resource-tags --region "$REGION" --key-id "$KEY_ARN" --output json \
  | jq -e '[.Tags[] | select(.TagKey == "workbench-production" and .TagValue == "true")] | length == 1' \
  >/dev/null || die "the created key does not carry workbench-production=true"

echo "$PARAMETER_ECHO" > "$ECHO_FILE"
echo
echo "── POINT OF NO RETURN ─────────────────────────────────────────────────────────"
echo "$PARAMETER_ECHO"
echo "── the next command is irreversible; the echo above is also in $ECHO_FILE ─────"
echo

ACTION_COUNT="$(echo "$PARAMETER_ECHO" | jq '.witness_actions | length')"
[ "$ACTION_COUNT" = "8" ] || die "the witness policy grants $ACTION_COUNT actions, not the ratified 8"

echo "Type exactly:  CREATE THE BUCKET"
read -r CONFIRM_BUCKET
[ "$CONFIRM_BUCKET" = "CREATE THE BUCKET" ] || \
  die "not confirmed at the point of no return; the KMS key exists and can be scheduled for deletion"

journal --argjson e "$PARAMETER_ECHO" '.parameter_echo = $e'

# ── 2. the witness bucket — IRREVERSIBLE ─────────────────────────────────────────────────────────────

log "creating the bucket with Object Lock enabled at creation"
# us-east-1 must NOT be sent as a LocationConstraint; every other region must be.
aws s3api create-bucket --region "$REGION" --bucket "$BUCKET" --object-lock-enabled-for-bucket

VERSIONING="$(aws s3api get-bucket-versioning --bucket "$BUCKET" --output json | jq -r '.Status // ""')"
[ "$VERSIONING" = "Enabled" ] || die "bucket reports versioning '$VERSIONING'; write-once does not hold"

log "applying $RETENTION_MODE / $RETENTION_DAYS days"
aws s3api put-object-lock-configuration --bucket "$BUCKET" \
  --object-lock-configuration "ObjectLockEnabled=Enabled,Rule={DefaultRetention={Mode=$RETENTION_MODE,Days=$RETENTION_DAYS}}"

aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

LOCK_JSON="$(aws s3api get-object-lock-configuration --bucket "$BUCKET" --output json)"
echo "$LOCK_JSON" | jq -e \
  --arg m "$RETENTION_MODE" --argjson d "$RETENTION_DAYS" \
  '.ObjectLockConfiguration.Rule.DefaultRetention | (.Mode == $m and .Days == $d)' >/dev/null \
  || die "the bucket did not report the ratified retention; STOP and investigate before proceeding"

journal --arg b "$BUCKET" --arg r "$REGION" --argjson l "$LOCK_JSON" \
  '.s3 = {bucket:$b, region:$r, versioning:"Enabled", object_lock:$l.ObjectLockConfiguration}'
log "bucket $BUCKET is now COMPLIANCE-locked for $RETENTION_DAYS days"

# ── 3. the standing role ─────────────────────────────────────────────────────────────────────────────

TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

# $WITNESS_POLICY was rendered in §1 and shown in the point-of-no-return echo. Installing exactly the
# document that was confirmed — rather than rebuilding an equivalent one here — is the whole reason it
# is built once: two constructions of "the same" policy are two things that can drift.

log "creating role $ROLE"
aws iam create-role --role-name "$ROLE" --assume-role-policy-document "$TRUST" \
  --description "Step 4D forward-validation witness (ADR 0047)" >/dev/null
aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY_NAME" \
  --policy-document "$WITNESS_POLICY"
# Host management is attached SEPARATELY and is excluded from the witness-authority analysis.
aws iam attach-role-policy --role-name "$ROLE" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"

ROLE_ARN="$(aws iam get-role --role-name "$ROLE" --output json | jq -r .Role.Arn)"
journal --arg a "$ROLE_ARN" --arg n "$ROLE" --argjson p "$WITNESS_POLICY" \
  '.iam = {role_arn:$a, role_name:$n, witness_policy:$p,
           attached_policies:["AmazonSSMManagedInstanceCore"]}'

# ── 3b. prove the boundary from the outside, before anything relies on it ────────────────────────────
#
# The runner cannot simulate its own policy (it holds no iam:SimulatePrincipalPolicy, correctly), so the
# operator does it here. Both directions matter: the eight actions must be allowed, and the destructive
# ones must NOT be — a role that can delete an object or weaken the lock defeats the whole boundary.

log "simulating the witness policy"
SIM='[]'
simulate() {  # $1 action, $2 resource, $3 expected decision
  local d
  d="$(aws iam simulate-principal-policy --policy-source-arn "$ROLE_ARN" \
        --action-names "$1" --resource-arns "$2" --output json \
        | jq -r '.EvaluationResults[0].EvalDecision')"
  printf '  %-46s %-28s %s\n' "$1" "$3" "$d"
  SIM="$(echo "$SIM" | jq --arg a "$1" --arg r "$2" --arg e "$3" --arg d "$d" \
        '. + [{action:$a, resource:$r, expected:$e, decision:$d, agrees:($d == $e)}]')"
}

for a in kms:GetPublicKey kms:Sign;                                      do simulate "$a" "$KEY_ARN" allowed; done
for a in s3:GetBucketLocation s3:GetBucketVersioning s3:GetBucketObjectLockConfiguration; do
  simulate "$a" "arn:aws:s3:::$BUCKET" allowed; done
for a in s3:PutObject s3:GetObject; do
  simulate "$a" "arn:aws:s3:::$BUCKET/$PREFLIGHT_PREFIX/x.json" allowed; done

# Must be denied. These are the properties the least-privilege claim actually rests on.
for a in s3:DeleteObject s3:DeleteObjectVersion s3:PutBucketVersioning \
         s3:PutBucketObjectLockConfiguration s3:BypassGovernanceRetention; do
  simulate "$a" "arn:aws:s3:::$BUCKET/$PREFLIGHT_PREFIX/x.json" implicitDeny; done
for a in kms:ScheduleKeyDeletion kms:DisableKey kms:CreateKey; do
  simulate "$a" "$KEY_ARN" implicitDeny; done

journal --argjson s "$SIM" '.iam.simulation = $s'
echo "$SIM" | jq -e 'all(.agrees)' >/dev/null \
  || die "the simulated permissions do not match the contract — STOP; see $JOURNAL"
log "permission contract verified in both directions"

# ── 4. the host ──────────────────────────────────────────────────────────────────────────────────────

AMI="$(aws ssm get-parameter --region "$REGION" \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --output json | jq -r .Parameter.Value)"
VPC="$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true \
  --output json | jq -r '.Vpcs[0].VpcId')"
SUBNET="$(aws ec2 describe-subnets --region "$REGION" --filters Name=vpc-id,Values="$VPC" \
  --output json | jq -r '.Subnets[0].SubnetId')"

log "creating the security group (egress HTTPS only, NO inbound)"
SG="$(aws ec2 create-security-group --region "$REGION" --vpc-id "$VPC" \
  --group-name "${HOST_NAME}-sg" \
  --description "Step 4D forward-validation host: outbound HTTPS only, no inbound" \
  --output json | jq -r .GroupId)"
aws ec2 revoke-security-group-egress --region "$REGION" --group-id "$SG" \
  --protocol -1 --port -1 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
aws ec2 authorize-security-group-egress --region "$REGION" --group-id "$SG" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 >/dev/null

log "launching $HOST_NAME"
# The default VPC has no NAT and no VPC endpoints, so an SSM-managed instance needs a public IP to
# reach the SSM endpoints at all — an internet gateway alone is not enough. There are no inbound rules,
# so the address is reachable by nothing.
INSTANCE_JSON="$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
  --subnet-id "$SUBNET" --security-group-ids "$SG" \
  --associate-public-ip-address \
  --iam-instance-profile "Name=$ROLE" \
  --metadata-options "HttpTokens=required,HttpEndpoint=enabled,InstanceMetadataTags=enabled" \
  --tag-specifications \
    "ResourceType=instance,Tags=[{Key=Name,Value=$HOST_NAME},{Key=workbench-purpose,Value=forward-validation},{Key=workbench-production,Value=true}]" \
  --output json)"
INSTANCE_ID="$(echo "$INSTANCE_JSON" | jq -r '.Instances[0].InstanceId')"

journal --arg i "$INSTANCE_ID" --arg t "$INSTANCE_TYPE" --arg a "$AMI" --arg s "$SG" \
        --arg n "$HOST_NAME" \
  '.host = {instance_id:$i, instance_type:$t, image_id:$a, security_group:$s, name_tag:$n}'
journal --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.completed_at = $t'

log "instance $INSTANCE_ID"
cat <<DONE

Provisioned. Resource identities are in $JOURNAL — copy it off before doing anything else.

  KMS key   $KEY_ARN
  bucket    $BUCKET   ($RETENTION_MODE / $RETENTION_DAYS days, IRREVERSIBLE)
  role      $ROLE_ARN
  host      $INSTANCE_ID  ($HOST_NAME)

Next, on the host (Step 4D plan §4 steps 5-9):
  1. install Python + the exact deployed commit into a clean virtualenv
  2. python -m app.validation.aws.production_witness install-key --key-arn $KEY_ARN \\
       --path /opt/workbench/witness/anchor_public_key.der --out install_key.json
  3. python -m app.validation.aws.production_witness attest     ...
  4. python -m app.validation.aws.production_witness preflight  ...
  5. python -m app.validation.aws.production_witness negatives  ...

⚠ Nothing above opens the forward window, records an observation, or authorizes Account-4 activation.
DONE
