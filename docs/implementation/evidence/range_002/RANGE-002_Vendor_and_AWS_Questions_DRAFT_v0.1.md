# RANGE-002 vendor storage and AWS-use questions — DRAFT for the owner to send

| Field | Value |
|---|---|
| Status | **DRAFT. NOT SENT.** The owner sends; no vendor or AWS contact has been made and no data has been fetched. `[MERGE NOT APPROVED]` |
| Default | **DENY.** Any unanswered question below keeps the corresponding fetch/storage action denied (see the record template in the same directory). |
| What each answer unblocks | Step 3 of the preparation chain: fetch authorization. Nothing here authorizes a fetch by itself. |

Evidence already on record (so questions are not asked twice): Alpaca's published pages state history "since 2016", 200/min (Basic) and 10,000/min (Algo Trader Plus) historical calls, `raw` default adjustment and the `asof` symbol-mapping parameter. They are **silent** on storage, caching, derived data, research use, cloud hosting, delisted symbols, and rate-limit scope. The Customer Agreement section "Use of Market Data" forbids reproducing, distributing or commercially exploiting data without written consent. Sharadar's documentation lists the `TICKERS` columns (primary key `table, permaticker, ticker`) and calls the table a snapshot; it does not state how historical ticker intervals, reuse or symbol changes are represented.

## A. Questions for Alpaca (Market Data)

| ID | Question (send verbatim) | Why it matters | Unblocks | If unanswered |
|---|---|---|---|---|
| ALP-1 | May we **store a local copy** of historical 1-minute SIP bars obtained through the Market Data API for **internal research and backtesting**, and for how long may we retain them? | The docs are silent; the Customer Agreement restricts "reproduce". | Any storage of fetched bars | DENY storage |
| ALP-2 | May that copy reside on **our own AWS infrastructure** (we will state the account and region)? | Hosting location is unstated. | Writing fetched bars to AWS | DENY |
| ALP-3 | May **statistics and reports derived** from the data (aggregates that do not reconstruct the bars) be shared with an **independent validator and outside reviewers**? | The validator must be able to see results. | Validator access to outputs | DENY sharing |
| ALP-4 | Are bars for **delisted and renamed symbols** retrievable, under which symbol (historical or current), and how does `asof` behave for a symbol that no longer exists? | Survivorship coverage is not stated. | Delisted-name coverage claim (F2) | Coverage stays UNKNOWN |
| ALP-5 | Is the 10,000 calls/min historical limit applied **per API key, per account or per endpoint** for our entitlement? | Scope is not stated. | Fetch-plan sizing | Plan at the lowest published rate |
| ALP-6 | Is each bar timestamp the **start** of its one-minute interval, in UTC, for the stocks bars endpoint? | The reference page does not state it; the kernel accepts start-stamped bars only. | Timestamp convention verification | Verify empirically before any use |
| ALP-7 | Does our use (an LLC running its own research and paper trading) affect our **subscriber classification** or the entitlement terms for SIP data? | The agreement distinguishes non-professional subscribers. | Entitlement reference | DENY |

## B. Questions for Sharadar / Nasdaq Data Link (identity history)

| ID | Question (send verbatim) | Why it matters | Unblocks | If unanswered |
|---|---|---|---|---|
| SHA-1 | Does a current pull of `SHARADAR/TICKERS` (`table=SEP`) carry **historical ticker intervals** per `permaticker`, or only the current ticker? What do `relatedtickers`, `firstpricedate` and `lastpricedate` denote per row? | Determines whether overwritten issuer history can be reconstructed from a pull. | Retention decision | RETAIN stays undecided |
| SHA-2 | How is a **ticker reused by a different company** after the first delisted represented in `TICKERS`, `SEP` and `ACTIONS`? | Reuse must not be collapsed. | Identity design | SCOPE_AMENDMENT |
| SHA-3 | How is a **symbol change** represented (is history re-keyed to the new ticker), and what are the exact `ACTIONS` action strings for ticker changes, listings and delistings? | `ACTIONS` is ticker-keyed with no `permaticker`. | Interval reconstruction | SCOPE_AMENDMENT |
| SHA-4 | May we **retain the raw `TICKERS` and `ACTIONS` rows** (with intervals) in our research store on AWS under our subscription? | Retention of raw rows is the remedy for the collapsed grain. | Storing raw identity rows | DENY |
| SHA-5 | Is there any **point-in-time / vintage** mechanism beyond `lastupdated`? | A snapshot cannot be backdated. | PIT claim wording | No PIT claim |

## C. AWS-use questions (answered by the owner / operator, not a vendor)

| ID | Question | Answer format |
|---|---|---|
| AWS-1 | Which **AWS account** (id) will hold any fetched or derived data? | 12-digit id |
| AWS-2 | Which **region**? | region code |
| AWS-3 | Which **service** and resource (for example one S3 bucket with Object Versioning, or the existing box)? | service + resource reference |
| AWS-4 | **Data class** of each object: vendor-licensed market data / vendor-licensed identity rows / derived aggregates / evidence. | one class per prefix |
| AWS-5 | **Retention** and deletion (matching ALP-1 / SHA-4)? | duration or "until vendor term ends" |
| AWS-6 | **Access:** which principals may read; is the validator given access to raw data or only derived outputs (ALP-3)? | role list |
| AWS-7 | **Integrity:** checksum and Version-ID pinning per GITHUB-OPS-001; encryption at rest? | yes/no + key reference |
| AWS-8 | **Who creates the resource**, and which dated owner record in Git authorizes it? | person + record path |

Reminder: AWS resource creation or use is withheld until a dated owner record exists in Git. These are questions, not requests to create anything.

## D. How the answers are used
Answers are copied, with the document reference and date received, into `RANGE-002_Fetch_Authorization_Record_TEMPLATE_v0.1.json`. `fetch_authorization_check.py` returns **DENY** unless every field is present and every required permission is an explicit `true`. Even `ALLOW` from the checker is only "the record is complete": it is not an authorization until the owner commits it as a dated record.
