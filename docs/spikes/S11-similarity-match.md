# Spike S11: similarity match on Semgrep findings

| | |
|---|---|
| Date | 2026-11-17 |
| Time spent | One session |
| Result | **Partly.** A rule match links the two SQL injections and rejects every unrelated finding. A snippet score, built as briefed, does not. |

## Question

Can a similarity match (normalized code snippet, rule or CWE filter first) link the login and search SQL injections from the S3 results, and reject unrelated findings, without a vector database? (From `docs/PLAN.md`, section 5.)

## What we did

- Cloned Juice Shop `v20.0.0` inside a labelled container volume. Nothing from the source is on the Mac.
- Reran Semgrep `1.185.0` (same pinned image and the same six rule sets as S3, `--metrics=off`) from the repo root with relative paths, excluding `data/static/codefixes/` and `.github/`. Files are in `spikes/S11/`.
- Python 3.13 standard library only, in a pinned container (the venv was not needed). The script reads the findings, cuts a window of lines around each finding, normalizes it and scores every pair.
- Normalization: drop comments and whitespace, then three variants.
  - **A:** identifiers become `ID`, strings and numbers become placeholders (the method as briefed).
  - **B:** like A, but SQL words inside template strings are kept and each `${...}` becomes `PH`.
  - **C:** comments and whitespace dropped only. Identifiers are kept. This is not the briefed method. I added it to see why A and B fail.
- Two scores: Jaccard on 3-token shingles (J) and `difflib` ratio on the token list (R).
- Window: the finding's lines plus 0, 1, 2 or 3 lines either side.
- No model call. `make clean-all` was run at the end.

Not committed: the Semgrep results (they stay in the volume, which `make clean-all` removes). The score files hold only finding locations and numbers. For the secret finding I record file, line and rule only.

## What happened

### The input

17 results at 15 locations in 825 files (S3 reported 35 because of the exclusions). Rule IDs and CWEs:

| Location | Rule ID(s) | CWE |
|---|---|---|
| `routes/login.ts:34` | `express-sequelize-injection`, `tainted-sql-string` | CWE-89 |
| `routes/search.ts:23` | `express-sequelize-injection`, `tainted-sql-string` | CWE-89 |
| `routes/redirect.ts:19` | `express-open-redirect` | CWE-601 |
| `routes/userProfile.ts:61` | `code-string-concat` | CWE-95 |
| `lib/insecurity.ts:56` (secret) | `hardcoded-jwt-secret` | CWE-798 |
| `routes/fileServer.ts:33`, `keyServer.ts:14`, `logfileServer.ts:14`, `quarantineServer.ts:14` | `express-res-sendfile` | CWE-73 |
| `server.ts:269`, `:273`, `:277`, `:281` | `express-check-directory-listing` | CWE-548 |
| `.npmrc:1`, `frontend/.npmrc:1` | `npm-missing-minimum-release-age` | CWE-829 |

The Trivy private-key finding (`lib/insecurity.ts:23`) is not a Semgrep result, so it is not in this test. Semgrep's secret finding is the JWT-secret rule at line 56.

### 1. Filter by rule or CWE

- The only two findings that have `express-sequelize-injection` or `tainted-sql-string` are login:34 and search:23.
- 105 pairs: 14 share a rule (the positive pair, 6 `sendfile` pairs, 6 directory-listing pairs, 1 `.npmrc` pair). 91 do not.
- **Rule match alone gives the positive link and no false link to anything in the brief's negative set.** Matching on CWE gives the same result (CWE-89 appears only on those two).
- OWASP category does not work as a filter. The same rules tag the SQL injections `A01:2017` and `userProfile` `A03:2021`, both called "Injection". Use the CWE.

### 2. Snippet score, as briefed (variants A and B)

Positive pair against the highest-scoring cross-rule pair (a pair that must not link), by window size:

| Window (lines either side) | Variant | Positive | Highest false pair | Pair | Separates? |
|---|---|---|---|---|---|
| 3 | A, J / R | 0.310 / 0.628 | 0.537 / 0.691 | `fileServer:33`–`redirect:19` | No |
| 3 | B, J / R | 0.295 / 0.639 | 0.537 / 0.691 | same | No |
| 0 | A, J / R | 0.250 / 0.615 | 0.579 / 0.833 | `login:34`–`server.ts:269`, `redirect:19`–`userProfile:61` | No |
| 0 | B, J / R | 0.235 / 0.667 | 0.333 / 0.833 | `redirect:19`–`userProfile:61` | No |
| 1 | B, J / R | 0.212 / 0.587 | 0.240 / 0.636 | `fileServer:33`–`redirect:19` | No |
| 2 | B, J / R | 0.253 / 0.568 | 0.324 / 0.571 | `fileServer:33`–`redirect:19` | No |

No threshold works for A or B at any window size. Unrelated Express handlers share arrow-function and `req`/`res` shape, and placeholders throw away the only words that tell the flaws apart. The SQL words in B did not help enough: the two injection windows share about five of them.

### 3. Why variant C separates, and why that is not a win

With identifiers kept (variant C) and a window of 0 or 1 lines, the positive pair separates:

| Window | Metric | Positive | Highest false pair | Gap |
|---|---|---|---|---|
| 0 | J | **0.257** | 0.051 (`login:34`–`server.ts:269`) | 0.206 |
| 0 | R | 0.667 | 0.421 | 0.246 |
| 1 | J | 0.189 | 0.059 | 0.130 |
| 2 | J | 0.121 | 0.155 | none |
| 3 | J | 0.188 | 0.278 | none |

The score separates because both lines contain `models.sequelize.query`. That is the same sink the Semgrep rule matched. So the snippet score re-discovers the rule, and it needs identifiers to do it.

### 4. Scores for the briefed test set (window 0, variant A as briefed, variant C as the best case)

All 105 pairs, with all four metrics, are in `spikes/S11/scores-ctx0.csv` (window 0) and `spikes/S11/scores-ctx3.csv` (window 3). The table groups them. Ranges are min to max over the pairs in the group.

| Pair group | Pairs | A, J | A, R | C, J | C, R | Linked at C, J ≥ 0.15? |
|---|---|---|---|---|---|---|
| **login:34 – search:23 (positive)** | 1 | 0.250 | 0.615 | **0.257** | **0.667** | **yes** |
| SQLi – `redirect:19` | 2 | 0.118–0.286 | 0.500–0.714 | 0.000 | 0.182–0.222 | no |
| SQLi – secret (`lib/insecurity.ts:56`) | 2 | 0.069–0.171 | 0.378–0.596 | 0.000 | 0.080–0.143 | no |
| SQLi – `userProfile:61` | 2 | 0.000 | 0.417–0.571 | 0.000 | 0.121–0.148 | no |
| SQLi – `sendfile` x4 | 8 | 0.200–0.273 | 0.645–0.762 | 0.000 | 0.176–0.250 | no |
| SQLi – directory listing x4 | 8 | 0.143–0.579 | 0.387–0.732 | 0.000–0.051 | 0.136–0.348 | no |
| SQLi – `.npmrc` x2 | 4 | 0.000 | 0.174–0.308 | 0.000 | 0.000 | no |
| `redirect` – secret | 1 | 0.111 | 0.343 | 0.000 | 0.114 | no |
| `redirect` – `userProfile` | 1 | 0.333 | 0.833 | 0.000 | 0.333 | no |
| Other cross-rule pairs (none is SQLi) | 65 | 0.000–0.333 | 0.118–0.833 | 0.000–0.044 | 0.000–0.421 | no |
| Same rule: `sendfile` x4 | 6 | 1.000 | 1.000 | 1.000 | 1.000 | yes |
| Same rule: directory listing x4 | 6 | 0.619–1.000 | 0.905–1.000 | 0.636–1.000 | 0.905–1.000 | yes |
| Same rule: `.npmrc` x2 | 1 | 1.000 | 1.000 | 1.000 | 1.000 | yes |

### 5. Threshold

For variant C, window 0, Jaccard on 3-token shingles: **0.15**. It sits between the highest false pair (0.051) and the positive (0.257). The margin comes from one positive pair, so it is a weak basis for a number. For variants A and B there is no threshold.

At 0.15 the links are the positive pair and the 13 same-rule sibling pairs. All 14 are exactly the pairs that share a rule ID. **The snippet score adds nothing beyond the rule match on this data.**

### 6. False links and misses

- **False links:** none at 0.15, window 0, variant C, among all 91 cross-rule pairs (redirect and the secret included). With variant A (Jaccard, window 0), a threshold that keeps the positive pair (0.250) also links 21 cross-rule pairs, 9 of them to a SQL injection (`login:34` with `server.ts` directory listings, `search:23` with `redirect:19` and three `sendfile` handlers). Variant B (Jaccard) links 13 cross-rule pairs; the ratio score on B links 1.
- **Misses:** none for the briefed positive pair with variant C at window 0 or 1. Raise the window to 2 or 3 and C misses it (0.121 and 0.188 against false pairs at 0.155 and 0.278).
- **Same-rule siblings** (13 pairs, such as `keyServer`–`logfileServer`) link at 0.64 to 1.0. They are the same rule in different files, so a link is probably right. The brief did not name them, so I count them as neither false links nor misses. The four `sendfile` windows are identical at window 0 and score 1.000, which says only that the handlers are copies.

### 7. Does it work on code written differently? (hand-written, not from a scan)

Three snippets I wrote, scored against login:34 and search:23 at window 0. They are not scan results. They test whether a score would link the same flaw in another codebase.

| Snippet | A, J vs login / search | C, J vs login / search |
|---|---|---|
| syn1: same flaw, same library (`db.sequelize.query` with a template string) | 0.200 / 0.556 | 0.219 / 0.222 |
| syn2: same flaw, other library (`pool.query("..." + id)`) | 0.174 / 0.308 | **0.026 / 0.031** |
| syn3: unrelated (`res.redirect(req.query.to)`) | 0.167 / 0.375 | 0.000 / 0.000 |

- Same library, renamed: C links it (0.22, above 0.15). A scores it no higher than syn3 for login (0.20 against 0.17).
- Other library: C misses it (0.03). A scores the unrelated redirect (0.375 for search) above the other-library SQL injection (0.308).
- This is three lines I wrote, so it shows direction only. It does not prove anything.

## Cost

None. No model API and no paid call. Semgrep rules were fetched from the registry at run time (free, no code uploaded).

## Decision

- **Answer: partly.** The two SQL injections link, and unrelated findings are rejected, but the rule match does that and the snippet score adds nothing. **Juice Shop cannot test code similarity under a different rule.** Both findings fire the same two rules, and no other finding shares them.
- For the memory ledger use the **CWE as the family filter, then the rule ID**. Do not build a snippet score yet.
- Snippet similarity as briefed (identifiers and literals replaced) does not work. A version that keeps identifiers works only when the sink name is shared, which is what the rule already tells us.
- **Recommend a second codebase** with the same flaw written under a different rule (the parking-lot item "Memory demo option C") before anyone relies on code similarity. Until then, say in every result note that the match is rule-based.
- No vector database was needed to reach this answer, and this spike gives no reason to add one. It does not show a vector index would work either.

## Surprises and risks

- **Window size matters a lot.** The same method at ±3 lines scores the injections below unrelated handlers. Boilerplate around the line (the Express handler wrapper) dominates. Affects M4-8.
- **The Semgrep secret rule fired on line 56, not the key at line 23.** A secret finding's window can hold the secret itself. Never print or store the normalized snippet of a secret finding. Affects M4-7.
- **OWASP tags differ between rules** for the same class (`A01:2017` and `A03:2021` both "Injection"). Use CWE. Affects M4-7 and M4-8.
- `userProfile` (CWE-95, code injection) is a different CWE from the SQL injections (CWE-89). A CWE-exact filter will not link them. A parent-class filter (CWE-74) might. Untested.
- Semgrep Rules License: no rule text copied. Only rule IDs and locations are kept. Nothing to publish.
- The M0-7 plan row for S11 is on a branch that is not merged yet. This branch is stacked on it (see Follow-up).

## Follow-up

Carry-overs:

- **M4-7 (memory ledger).** Key each record on CWE plus rule ID(s) plus file and line. Do not store snippets. If a snippet is wanted, store a hash, and never for a secret finding. Record `scanner`, `rule_id`, `cwe` and `path` so a later match can use them without a model call.
- **M4-8 (cross-reference).** Filter on CWE (then rule ID) first. Use any snippet score only to rank matches inside that family, not to decide a link. Show the match as evidence with the rule and CWE named, since a developer approves it (already in the task). Test on a second codebase before claiming similarity works across repositories. Use a window of 0 lines if a snippet score is added, and keep identifiers.
- Same-rule siblings in one repository (`sendfile`, directory listing) will link to each other. Decide in M4-8 whether to group them or show one comment per finding.

Not added to `docs/PLAN.md` as rows, for the owner to decide:

- A small spike (S11b) on a second codebase with the same flaw under a different rule. This is the parking-lot item "Memory demo option C".
