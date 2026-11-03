# SANTRA Source Quality & Evidence Verification Report

## 1. Source Authority Hierarchy
SANTRA categorizes discovered sources according to domain trustworthiness and assigns calibrated base authority weights:

| Source Type | Examples | Base Authority Score |
| :--- | :--- | :---: |
| `OFFICIAL_DOCS` / `OFFICIAL_MANUFACTURER` | python.org, nvidia.com, microsoft.com | 0.95 |
| `GOVERNMENT_REGULATORY` | bis.gov.in, traai.gov.in, who.int | 0.95 |
| `ACADEMIC_RESEARCH` | arxiv.org, ieee.org, nature.com | 0.90 |
| `REPUTABLE_TECH` | anandtech.com, tomshardware.com, xda-developers.com | 0.85 |
| `ESTABLISHED_NEWS` | thehindu.com, indianexpress.com, reuters.com | 0.85 |
| `RETAILER_MARKETPLACE` | amazon.in, flipkart.com, croma.com | 0.80 |
| `INDEPENDENT_REVIEWER` | rtings.com, notebookcheck.net | 0.80 |
| `COMMUNITY_FORUM` | reddit.com, stackoverflow.com | 0.65 |
| `UNVERIFIED` | generic blogspot, unrated aggregators | 0.50 |

---

## 2. Contradiction Detection & Conflict Resolution

### Detection Mechanism
Claims are grouped by `(entity_name, metric_name)`:
- If distinct metric values are discovered across sources (e.g. Battery Life: "4 hours" vs "10 hours"):
  - If the higher-confidence source exceeds the competitor by `>= 0.25`:
    - Top source marked `ConflictStatus.CONFLICT_RESOLVED`, `VerificationStatus.VERIFIED` (or `VERIFIED_BY_PRIMARY_SOURCE`).
    - Inferior source marked `ConflictStatus.CONFLICT_RESOLVED`, `VerificationStatus.CONTRADICTORY`.
  - If confidence differential is `< 0.25`:
    - Both marked `ConflictStatus.CONFLICT_UNRESOLVED`.
    - If `metric_name == "price_inr"`: Legitimate market variance is recognized; both remain `VerificationStatus.VERIFIED`.
    - Otherwise: Marked `VerificationStatus.CONTRADICTORY` and surfaced to Nemotron reasoning.

---

## 3. Syndicated Copy & Echo-Chamber Detection
- **Mechanism**: `SourceVerifier._detect_syndicated_copy()`
- When two different domains report identical or near-identical excerpt text (>= 40 characters), the engine recognizes that the secondary domain is re-publishing wire copy (PTI, ANI, PR Newswire) rather than independently investigating.
- **Penalty**: The secondary excerpt's confidence score is discounted by 15% (`confidence * 0.85`), preventing syndicated PR loops from artificially boosting confidence.

---

## 4. Verification Status Taxonomy
- `VERIFIED_BY_PRIMARY_SOURCE`: Direct statement from official documentation or manufacturer hardware specs.
- `CORROBORATED`: Independently confirmed across two or more distinct domains with unique text.
- `CONFLICTING` / `CONTRADICTORY`: Contradicted by another discovered source with equal or greater authority.
- `OUTDATED`: Source timestamp or content indicates superseded software or hardware revisions.
- `INSUFFICIENT_EVIDENCE`: Solitary claim from low-authority source (`confidence < 0.60`).
- `UNVERIFIED`: Initial state pending verification pass.

