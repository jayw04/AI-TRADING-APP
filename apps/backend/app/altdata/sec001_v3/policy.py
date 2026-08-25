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

# Acquisition status vocabulary. Every distinction here is load-bearing, because each one
# separates a fact about the SOURCE from a fact about OUR MACHINERY. Collapsing any pair
# launders one into the other -- which is precisely how an extraction defect becomes
# apparent historical missingness.
#
# None of these mean ``no_pit_sic``. That is a downstream determination about historical
# evidence, made only after the source bytes have been inspected.
ACQ_HEADER_INDEX: Final = "HEADER_INDEX"
"""-index-headers.html served the header directly."""

ACQ_HEADER_TERMINATED: Final = "HEADER_TERMINATED"
"""``</SEC-HEADER>`` was actually observed. The header is bounded and complete."""

ACQ_DOCUMENT_EOF_NO_TERMINATOR: Final = "DOCUMENT_EOF_NO_SEC_HEADER_TERMINATOR"
"""The complete document was acquired, but no closing SEC-header tag exists in it.

A SOURCE-FORMAT fact, not evidence completeness. Measured on ABT accession
0000912057-00-024277: all 28,350 bytes retrieved, no terminator anywhere, no SIC. Raising
the byte ceiling cannot fix this -- there is nothing further to read."""

ACQ_HEADER_INCOMPLETE: Final = "ACQUISITION_HEADER_INCOMPLETE"
"""Neither terminator nor authoritative EOF reached before the frozen ceiling. OUR failure."""

ACQ_ENCODING_UNSUPPORTED: Final = "ACQUISITION_ENCODING_UNSUPPORTED"
"""An encoded representation reached, or would have reached, the frozen parser.

Defect E (ruling e88ea53). Ranged requests are sent with ``Accept-Encoding: identity`` so
that range offsets refer to document bytes, which is what the frozen spine assumes. If a
server nonetheless returns an encoded representation, or decoding fails, acquisition fails
CLOSED under this status. It is OUR machinery failure, never historical missingness."""

#: Forced on the legacy ranged fallback so range offsets refer to DOCUMENT bytes. Range plus
#: Content-Encoding makes offsets refer to the COMPRESSED representation, which is what fed
#: gzip fragments to the parser across three canaries.
RANGED_ACCEPT_ENCODING: Final = "identity"

# -- Defect F: bounded response consumption (ruling 7C) --------------------------------
# Defect F: SEC answered every identity-encoded ranged request with 200 and the WHOLE
# document. The old ceiling bounded only what the client ASKED for, never what a response
# could DELIVER, so a 4 KiB request pulled 422 MB. These bound actual consumption.

# Hard ceiling on bytes pulled from a single response stream. Chunk granularity means the
# final chunk may cross the line, so the guarantee is "no further chunk is requested once
# the ceiling is reached", not a byte-exact stop. wire_bytes_consumed records the truth.
RESPONSE_CONSUMPTION_CEILING_BYTES: Final = HEADER_COMPLETION_CAP_BYTES  # 1 MiB

# Maximum bytes the PINNED transport can pull from the socket in one chunk.
# PROVED, not assumed: httpcore's HTTP/1.1 connection reads via
#   data = self._network_stream.read(self.READ_NUM_BYTES, timeout=timeout)
# with ``READ_NUM_BYTES = 64 * 1024`` (httpcore 1.0.9,
# httpcore/_sync/http11.py:44). test_defect_f_bounded_transport asserts this
# against the installed httpcore, so a version bump that changes it fails loudly
# instead of silently widening the overshoot.
MAX_UPSTREAM_CHUNK_BYTES: Final = 64 * 1024

# Guard band: stop requesting chunks this far below the hard ceiling, so that even
# a maximal final chunk cannot carry actual consumption above it.
#   consumed <= (STOP - 1) + MAX_UPSTREAM_CHUNK_BYTES < RESPONSE_CONSUMPTION_CEILING_BYTES
CONSUMPTION_STOP_THRESHOLD_BYTES: Final = (
    RESPONSE_CONSUMPTION_CEILING_BYTES - MAX_UPSTREAM_CHUNK_BYTES
)

# Explicit ranged-response classification. There is no implicit third success state:
# anything not classifiable here is refused.
RANGE_CLASS_206_VALIDATED: Final = "206_VALIDATED"
RANGE_CLASS_200_IGNORED: Final = "200_FULL_RANGE_IGNORED"
RANGE_CLASS_UNRANGED: Final = "UNRANGED"

# Refusal reasons -- fail closed, never a silent success.
RANGE_REFUSAL_206_NO_CONTENT_RANGE: Final = "206_WITHOUT_CONTENT_RANGE"
RANGE_REFUSAL_206_INCONSISTENT: Final = "206_CONTENT_RANGE_INCONSISTENT_WITH_REQUEST"

#: Encodings that mean "no transformation was applied".
IDENTITY_ENCODINGS: Final[frozenset[str | None]] = frozenset({None, "", "identity"})

#: A parser-facing body may never begin with these bytes.
GZIP_MAGIC: Final = bytes((0x1F, 0x8B))

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
