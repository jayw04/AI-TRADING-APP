# Defect-F Governed Canary — Reproducibility Artifacts

Custodied under the standing ruling `PASS2_REPRODUCIBILITY_ARTIFACTS — CUSTODY REQUIRED BEFORE
TEARDOWN`, applied to the canary host by the same standard: the script that produced a result is
custodied alongside the result, so reproducibility does not depend on a working-tree copy.

Every digest below was verified **identical to the file on the ephemeral canary host
`i-073001108a2aa7136` before that host was destroyed**. Committed under `* -text -diff` so the
blobs are byte-exact.

| file | bytes | sha256 | role |
|---|---:|---|---|
| `canary_result.json` | 1,813 | `7ef617ff98b5a1705cf5a34238877f41e4d512bef486d75f4ec84cc21fd40026` | the machine-readable result and all nine assertions |
| `canary.py` | — | `56d2390747d17365d1216f175140c67b08631120af9665d4cbd5902797afbe27` | the exact script that issued the single governed request |
| `gate.py` | — | `aeb13e39e9860eee4f343a0a051a23c21022ae5063832239dfbc418893027a7d` | pre-flight dependency gate (httpx/httpcore/READ_NUM_BYTES/http11 sha256) |
| `verify_blobs.py` | — | `a02d59cacaeb07bc8bc0c306b8250594a1587c0cb3381eb7015f6891bd183a80` | on-host blob verification against `517cab0` — the check that caught the `git archive` CRLF defect |

Not custodied because reproducible from a pinned source: the payload tarball (rebuildable from
`517cab0` with `git -c core.autocrlf=false -c core.eol=lf archive`), the pip `site` tree (pinned
versions recorded in the result), and `get-pip.py` (upstream).

Binds artifacts only. States no conclusion and reopens nothing. The canary verdict lives in
`SEC001_V3_DefectF_GovernedCanary_Result_v1_0.md`.
