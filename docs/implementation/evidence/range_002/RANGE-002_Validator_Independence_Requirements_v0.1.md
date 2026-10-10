# RANGE-002 Validator Independence Requirements v0.1 (REQUIREMENTS ONLY)

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. Nothing here is a decision.** Every item labelled "Recommendation (not a decision)" is a recommendation only. No code, key, AWS call or IAM change is authorized by this document. |
| Date | 2026-10-10 |
| Purpose | Define how actual independence of the sign-off roles is confirmed *outside* the R1-L1b string-comparison safeguard |
| Related | Approval Signing and Verification Design v0.1 (commit d1406ec2, sections 5, 7, 9); Decision Sheet D08; R1-L1b change (`fix/range002-signoff-distinct-roles`, merge not approved) |
| Rule R9 | No agent holds a role, a key, a principal, or fills a sign-off row. |

Section ids (V-1 ... V-9) are stable; other documents may cite them.

---

## V-1. What the string-comparison safeguard proves, and what it does not

The R1-L1b safeguard (Level 1) refuses a freeze when `signoff.owner`, `signoff.trading_expert` and `signoff.independent_validator` are not pairwise distinct after Unicode normalisation (NFKC, casefold, strip, whitespace collapse).

It proves only: **three different strings were typed.** It does not prove:

- that the strings name real people, or that any named person agreed to be named;
- that two different strings are two different humans (aliases, nicknames, email vs display name, `Alice Smith` vs `Smith, Alice`, and homoglyphs are not unified; invisible characters are refused, see V-7.1);
- that the validator did not write the engine or the spec, saw no results, or is free of conflicts;
- that the named person (rather than whoever can edit the draft file) approved anything. `signoff` is three typed strings and sits outside `spec_sha256`.

Recommendation (not a decision): treat the safeguard as a typo and copy-paste guard only, never as evidence of independence.

## V-2. Procedural confirmations the owner could require

Each row is a candidate requirement. The owner selects which apply (V-8); none is selected here.

| Id | Confirmation | Evidence form | Verified by |
|---|---|---|---|
| V-2.1 | Named natural persons: full legal name, role, and a contact route for each of owner / trading expert / validator; the three are different individuals | Roster document in the sign-off packet, hash-pinned | Owner (roster); validator checks roster against own identity |
| V-2.2 | Validator attests no authorship of, and no commit to, the engine (`app/research/range002/`), the spec or the freeze tooling | Signed attestation naming repo and the commit/author list reviewed | Owner, using a repo author list produced by someone other than the validator |
| V-2.3 | Validator attests no prior exposure to RANGE-002 results (holdout, candidate rankings, exposure ledger contents) | Attestation plus reconciliation with the exposure ledger | Owner; ledger custodian |
| V-2.4 | Separate accounts and credentials: distinct login identities, distinct machines or profiles for signing, no shared password manager vault, no shared MFA device | Attestation; key-ceremony record | Validator for own setup; owner for others |
| V-2.5 | Separate custody of signing keys (Level 2): each role holds its own key; no role can sign with another's key; key administrators are not signers | Key policy snapshot hash, ceremony log, CloudTrail reconciliation (design section 5) | Validator, plus key administrator who is none of the signers |
| V-2.6 | Recorded conflicts-of-interest statement per signer: financial or employment ties to the owner or to GlobalComplyAI, LLC, family or reporting relationship, past or planned involvement in strategy development | Signed statement, blank-if-none stated explicitly | Owner reviews; for the owner's own statement, validator reviews |
| V-2.7 | Relationship disclosure: whether the trading expert and validator are employed, paid or directed by the owner, and by whom the validator is paid | Statement in the roster | Validator and owner |
| V-2.8 | The validator controls review of the public-key allowlist and its pin; the validator's own key fingerprint is exchanged over a separate channel | Pin record; ceremony notes (design section 7.1) | Owner counter-confirms validator-key changes |
| V-2.9 | Independent environment: the validator re-runs verification on a machine and account separate from the research tree | Validator environment record, verifier output hash | Validator |
| V-2.10 | Change control: any replacement of a signer after freeze is a recorded event with the same confirmations | Roster version history | Owner |

Recommendation (not a decision): V-2.1, V-2.2, V-2.3, V-2.6 as minimum for any real freeze; V-2.4/V-2.5 once Level 2 exists.

## V-3. Who verifies

| Question | Candidate verifier | Limit |
|---|---|---|
| Is the validator independent of the engine author? | Owner, or a party other than validator and engine author | The owner may be conflicted; if the owner authored or directed the engine, independence is relative to that |
| Is the owner distinct from the validator? | Third party or trading expert acknowledgement | Three-way cross-checks are only as strong as the roster |
| Are the keys held separately? | Key administrator (not a signer) plus CloudTrail review | Administrator can change policy; detection is after the fact |
| Is an attestation true? | Nobody, technically | Attestations are accountability devices, not proof |

Recommendation (not a decision): record, per confirmation, the named verifier and the date; a self-verified row is marked "self-attested".

## V-4. What the software can and cannot check

**Can (Level 1, now):** the three identifier strings are non-blank, free of invisible/control characters (V-7.1), pairwise distinct after normalisation; the spec hash is intact; frozen file with colliding or missing roles reports `is_signed` False.

**Can (Level 2, future, per signing design):** three distinct `key_id` and `person_id` values; each signature verifies against a validator-pinned public-key allowlist; a record binds spec hash, role, purpose and document hashes; replay and expiry checks.

**Cannot, at any level:** that a key's holder is the named person; that two keys are not controlled by one person; that the validator is free of conflicts or did not see results; that a signer read what they signed (blind signing remains procedural); that an administrator did not alter key policy (detect only).

Recommendation (not a decision): do not describe any software output as "independence verified"; use "distinct identifiers" (Level 1) or "distinct pinned keys" (Level 2).

## V-5. Interplay with D08 separation-of-duties options

**V-5.1 Exact definitions**, quoted verbatim from section 9 of `RANGE-002_Approval_Signing_and_Verification_Design_v0.1.md` at commit d1406ec2 (none selected):

| Option | Rule | Enforced by | Weakness |
|---|---|---|---|
| SoD-A | Three distinct humans, three distinct keys, for owner / trading expert / validator | Distinct `key_id` and `person_id` (technical) + identity attestation (procedural) | Technical check cannot prove two keys are two people |
| SoD-B | Owner and trading expert may be the same person; validator must be a different person | Same, with explicit recorded waiver | Per D08 sheet: D19 candidate review is then not independent of the final approver |
| SoD-C | Validator must also be distinct from the research lead and from whoever wrote the engine | Procedural + signed attestation by the validator | Needs a recorded engineer list |
| SoD-D | Any role overlap permitted | n/a | Defeats independent review; shown only for completeness |

**V-5.2 How the R1-L1b software check relates to each option.** The check is Level 1: strict all-pairs distinct identifier strings after normalisation, plus refusal of invisible/control characters. It authenticates nobody.

| Option | Relation to the R1-L1b check | Remaining procedural / Level 2 |
|---|---|---|
| SoD-A | Compatible and the nearest match: three different strings are required. Necessary, nowhere near sufficient. | V-2.1 to V-2.6; distinct keys and `person_id` are Level 2 |
| SoD-B | **Inexpressible.** R1-L1b refuses owner == trading_expert, so a freeze cannot run under SoD-B without a new owner decision, an amendment of the check and a recorded waiver. Do not work around it (for example by typing a trivially different string for the same person: that defeats the purpose and is not detected). | Waiver record; D19 independence caveat |
| SoD-C | Compatible: the check enforces only the three-way distinctness part. It knows nothing about the research lead or engine authors. | V-2.2, V-2.3 attestations; engineer list; verifier per V-3 |
| SoD-D | **Contradicted:** any overlap is refused. | none |

Recommendation (not a decision): SoD-A as target and SoD-C as minimum, as in the signing design; confirm that the owner intends R1-L1b's stricter all-pairs rule before merge, since it forecloses SoD-B at the code level.

## V-6. What is deferred to Level 2 signing

- Cryptographic, role-attributed, content-bound approvals; distinct `key_id` enforcement; key allowlist and validator pin; CloudTrail reconciliation; replay protection; revocation.
- Replacement of typed names by names derived from verified `person_id`.
- Technical enforcement that the approval keys are inaccessible to the agent and research environments.

Until Level 2 exists, V-2 confirmations are the only independence evidence and they are procedural.

## V-7. Gaps in the Level 1 safeguard that procedure must cover meanwhile

**V-7.1 F1 resolution (invisible characters).** The review found that zero-width and other invisible characters let `alice` and `ali<U+200B>ce` pass as distinct. The code change now applies a deterministic Unicode policy: a role identifier containing a non-whitespace code point of general category Cc, Cf or Cs, or an explicit list of default-ignorable code points (Hangul and Khmer fillers, braille blank, combining grapheme joiner, variation selectors, Mongolian FVS), is **refused at freeze and reported by `load_frozen` as unusable**; it is not silently stripped. Real whitespace is still collapsed. Code points are reported as `U+XXXX`. A legitimate name that needs ZWNJ/ZWJ would be refused; use an ASCII roster identifier.

**V-7.2 Still not covered by software:** homoglyphs (Cyrillic vs Latin), aliases, email vs display name, name-order variants (`Alice Smith` vs `Smith, Alice`), trailing punctuation, transliterations. Recommendation (not a decision): the roster (V-2.1) fixes one canonical identifier per person, copied into the spec, so a mismatch is visible on review.

## V-8. Owner selection table (all rows blank; no agent fills this)

| Id | Required for real freeze? (Yes / No / Waived with reason) | Named verifier | Decision date | Initials |
|---|---|---|---|---|
| V-2.1 | | | | |
| V-2.2 | | | | |
| V-2.3 | | | | |
| V-2.4 | | | | |
| V-2.5 | | | | |
| V-2.6 | | | | |
| V-2.7 | | | | |
| V-2.8 | | | | |
| V-2.9 | | | | |
| V-2.10 | | | | |

| D08 option selected (SoD-A / B / C / D) | Owner signature | Date |
|---|---|---|
| | | |

## V-9. Open questions for the owner

1. Does the owner confirm the all-pairs distinct rule (forecloses SoD-B in code)?
2. Who is the intended validator and how is that person remunerated and directed (V-2.7)?
3. Is a third-party verifier available for V-2.2/V-2.3, or is owner verification accepted as "self-attested"?
4. Is refusing (rather than stripping) invisible characters, as implemented in V-7.1, accepted?
5. Which of these confirmations must exist before Level 2 is built, versus only after?

Cross-reference for the P0 decision register / signature matrix: cite sections V-2 (confirmations), V-5 (D08 interplay), V-8 (selection table).
