"""SEC-001 V3 classification crawl — the frozen policy surface.

Every constant here is owner-ruled and pre-crawl frozen. Nothing in this module may be
widened, relaxed, or made configurable at call time: the crawl's whole evidentiary value
rests on the parameters having been fixed *before* any EDGAR request was issued, and on
this file being hashed into the pre-crawl manifest.

Governing records:
  - SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md            (theta values; anti-peek controls)
  - SEC001_V3_ResearchHost_PreAcquisitionRecord_v1_0.md  (host + bucket)
  - Amendment A (32bc34e) / Amendment B (91d1f1b) / Build Record v1.1 (cad13e6)

Scope boundary, stated once and enforced mechanically in ``forbidden.py``: this crawl
produces **facts** — one row per EDGAR document actually retrieved, and the effective-dated
SIC segments those rows imply. It computes no coverage statistic and no economic quantity.
Coverage adjudication is a separate one-shot artifact that spends the coverage freeze token
``5b26ffa2…``; that token is UNSPENT and this driver must never touch it.
"""

from __future__ import annotations

from typing import Final

# --- identity -------------------------------------------------------------------------

CRAWL_ID: Final = "SEC001_V3_CLASSIFICATION_CRAWL_V1"
CAPTURE_DATE: Final = "2026-08-24"

# --- what is fetched ------------------------------------------------------------------

# Owner-ruled 2026-08-24. The MR-002 spine's DEFAULT_FORMS is the 10-K/10-Q family only;
# V3 widens it through the *existing* ``forms=`` parameter — no MR-002 file is modified.
# 8-K is deliberately absent: the spine never used it and adding it is a silent scope
# expansion. 20-F / 40-F and their amendments rank 9 under the frozen
# ``_FORM_RANK.get(form, 9)`` fallback, i.e. below every 10-K/10-Q variant, which is the
# already-frozen "10-K > 10-Q > other forms" precedence applied unchanged.
FORMS: Final[tuple[str, ...]] = (
    "10-K", "10-K/A",
    "10-Q", "10-Q/A",
    "20-F", "20-F/A",
    "40-F", "40-F/A",
)

# Registered crawl change: extend history to 2000-01-01 (CoverageFreeze v1.0 §6).
CRAWL_SINCE: Final = "2000-01-01"

# --- fair-access policy ---------------------------------------------------------------

# SEC's published ceiling is 10 rps. We run at half that, from a single host, so that a
# transient burst cannot cross the ceiling. 5.0 -> EdgarClient._min_interval == 0.2s.
RATE_LIMIT_PER_SEC: Final = 5.0
SINGLE_HOST: Final = True

# Exact declared User-Agent. SEC fair access requires org + contact.
USER_AGENT: Final = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"

# GET is the only verb this crawl may issue. Enforced in fetch.py.
ALLOWED_METHODS: Final[frozenset[str]] = frozenset({"GET"})

# --- failure policy -------------------------------------------------------------------

# 403 is SEC telling us we are blocked. It is never retried, never backed off, never
# "worked around". The crawl halts, state is preserved, and a human must resume.
HALT_STATUSES: Final[tuple[int, ...]] = (403,)
HALT_COOLDOWN_SECONDS: Final = 600  # >= 10 minutes before a resume is even permitted

# 429 and transient 5xx are retried with bounded, jittered exponential backoff. The
# backoff lives here in the V3 driver, never in the pinned client.py (6c1d7006…), which
# deliberately has none.
RETRY_STATUSES: Final[tuple[int, ...]] = (429, 500, 502, 503, 504)
RETRY_MAX_ATTEMPTS: Final = 5      # 1 initial attempt + 4 retries
RETRY_BASE_DELAY_SECONDS: Final = 1.0
RETRY_MAX_DELAY_SECONDS: Final = 60.0
RETRY_JITTER_FRACTION: Final = 0.25  # full delay in [d*(1-f), d*(1+f)]

# Deterministic jitter: seeded per crawl so a resumed or replayed crawl reproduces its
# own backoff schedule. Randomness here is for server politeness, not for sampling.
JITTER_SEED: Final = f"{CRAWL_ID}:{CAPTURE_DATE}"

# --- SEC-header completion override (Remediation Ruling v1.0 §1) -----------------------

# The frozen spine falls back to the full-submission .txt with this exact legacy Range when
# an accession has no ``-index-headers.html`` (true for pre-~2014 filings). Measured on the
# 2026-08-24 canary: the SIC line is NOT inside the first 4 KiB, so every such fetch
# succeeded and yielded no SIC -- a perfect 53/53 split against index-header fetches. Left
# alone that turns an extraction defect into apparent historical missingness, which would
# feed straight into the >=20-year span provision of the coverage gate.
LEGACY_HEADER_RANGE: Final = "bytes=0-4095"

# Bounded progressive windows (cumulative end offsets), never a whole-file fetch. The first
# window is byte-identical to the spine's own request, so the common case costs exactly what
# it did before.
HEADER_COMPLETION_WINDOWS: Final[tuple[int, ...]] = (4096, 16384, 65536, 262144, 1048576)

#: Frozen absolute cap. Reaching it is an ACQUISITION failure, never an evidentiary fact.
HEADER_COMPLETION_CAP_BYTES: Final = 1048576  # 1 MiB

#: Frozen ceiling on range requests per filing. A server that serves short ranges could
#: otherwise turn one filing into hundreds of requests against the fair-access budget.
#: Exceeding it is an ACQUISITION failure, not an evidentiary fact.
HEADER_COMPLETION_MAX_REQUESTS: Final = 8

#: The override stops here. This subsumes both sanctioned stop conditions -- a SIC-bearing
#: header and a header legitimately without one are both *complete* at this tag -- which
#: keeps ALL SIC interpretation with the frozen spine and none in the transport layer.
SEC_HEADER_CLOSE_TAG: Final = "</SEC-HEADER>"

# Acquisition status vocabulary. The distinction between the last two is load-bearing:
# ``no_pit_sic`` is a fact about available historical evidence; ACQUISITION_HEADER_INCOMPLETE
# is a failure of our machinery and must NEVER count against classification coverage.
ACQ_HEADER_INDEX: Final = "HEADER_INDEX"                       # -index-headers.html served it
ACQ_HEADER_COMPLETE: Final = "HEADER_COMPLETE"                 # full SEC-HEADER obtained
ACQ_HEADER_INCOMPLETE: Final = "ACQUISITION_HEADER_INCOMPLETE"  # cap hit; NOT no_pit_sic

# --- where output may go --------------------------------------------------------------

# The only two prefixes this driver may write. ``sealed/`` holds the governed store and is
# off-limits: writing there would mutate an artifact under COMPLIANCE retention.
RAW_PREFIX: Final = f"raw/edgar/{CAPTURE_DATE}"
BUILD_PREFIX: Final = f"build/classification/{CAPTURE_DATE}"
ALLOWED_OUTPUT_PREFIXES: Final[tuple[str, ...]] = (RAW_PREFIX, BUILD_PREFIX)
FORBIDDEN_OUTPUT_PREFIXES: Final[tuple[str, ...]] = ("sealed/", "manifests/", "build/source/")

RESEARCH_BUCKET: Final = "workbench-sec001-v3-research-219024422756"

# --- the coverage-freeze token (must remain unspent) ----------------------------------

COVERAGE_FREEZE_TOKEN_PREFIX: Final = "5b26ffa2"
