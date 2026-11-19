# Spike S3: scanners against Juice Shop

| | |
|---|---|
| Date | 2026-11-12 |
| Time spent | One session, inside the timebox |
| Result | Yes |

## Question

Do Semgrep, Trivy and ZAP run in Docker against Juice Shop and produce SARIF? Which 3 to 5 findings do we curate?

## What we did

- Cloned Juice Shop at tag `v20.0.0` inside a container into a labelled Docker volume. Nothing from the source is on the Mac, and `npm install` was not run anywhere.
- Ran Semgrep, Trivy and ZAP as one-shot containers from `spikes/S3/compose.yaml`. All carry the project label and sit on `project-net`. Nothing publishes a host port. Results went to a labelled volume.
- `spikes/S3/run.sh` times each run and samples memory about once a second. It writes `spikes/S3/results.log`.
- ZAP scanned only `http://juice-shop:3000`, our own container, by its name on the project network.
- Full SARIF files stayed out of git. They were copied to a scratch folder outside the repo for analysis. This note holds short excerpts.
- No paid call was made. `make clean-all` was run at the end.

## What happened

### Images

All four are pinned by tag and digest, run natively on arm64, and are listed in `spikes/pulled-images.txt`.

| Tool | Image and version | Native arm64 | Digest (index) |
|---|---|---|---|
| Semgrep Community Edition | `semgrep/semgrep:1.185.0` | yes | `sha256:67518c17…` |
| Trivy | `aquasec/trivy:0.76.2` | yes | `sha256:8f6bb947…` |
| ZAP | `zaproxy/zap-stable:2.17.0` | yes | `sha256:9624669d…` |
| git (clone only) | `alpine/git:v2.54.0` | yes | `sha256:6a1fdb96…` |

The full digests are in `docs/ENVIRONMENT.md`.

### Per scanner

| Scanner | Run | Wall time | Peak memory | Output |
|---|---|---|---|---|
| Semgrep | `semgrep scan` on the source | 43.5 s | 626 MiB | JSON and SARIF |
| Trivy, source | `trivy fs --scanners vuln,secret` | 13.5 s | 80 MiB | JSON, then `trivy convert` to SARIF (0.3 s) |
| Trivy, image | `trivy image --image-src remote` | 6.6 s | 74 MiB | JSON, then SARIF (0.2 s) |
| ZAP baseline | `zap-baseline.py -m 2` | 45.5 s | 830 MiB | JSON, XML, HTML |
| ZAP SARIF | Automation Framework plan, spider 1 min | not timed (the spider took 18 s) | not measured | SARIF |

Memory is the highest value from samples taken about once a second, so short runs may be under-read. The Rancher VM has 3.8 GiB, so ZAP and Semgrep each fit, but not comfortably alongside a lot else.

### Semgrep

- **Rule sets (all from the Semgrep Registry):** `p/javascript`, `p/typescript`, `p/nodejs`, `p/expressjs`, `p/owasp-top-ten`, `p/secrets`.
- **Run flags:** `--metrics=off`. The registry rules are fetched at run time. No code is uploaded.
- **Licence of the engine:** LGPL-2.1.
- **Licence of the rules:** Semgrep Rules License v1.0 (read from the rules repository and the licence page). In short: use for your own internal business purposes only; do not distribute the rules or offer them to others as a service; keep the licence notices on any copy; mark any modified copy. See "Surprises and risks".
- **Result:** 35 findings across 1,000 scanned files. By the severity Semgrep reports: 19 ERROR, 14 WARNING, 2 MEDIUM. Where they sit: 15 in running app code (`routes/`, `lib/`, `server.ts`), 8 in `data/static/codefixes/` (teaching snippets, not live code), 10 in `.github/workflows/`, and 2 on `.npmrc`.
- **Errors:** 43 warnings, none fatal. They are partial-parse or syntax errors on the deliberately broken `codefixes/` snippets, HTML templates and workflow files, and one timeout. None are on `routes/login.ts`.
- **SARIF:** valid 2.1.0. Results carry no `level`; severity is in the native JSON. File paths are absolute (`/src/juice-shop/...`) because we scanned an absolute path. Scan from the repo root with a relative path to get repo-relative paths.

### Trivy

- **Source scan:** 0 dependency vulnerabilities, 3 secrets (1 HIGH, 2 MEDIUM). **This is not a clean bill.** Juice Shop has no lockfile on purpose (`.npmrc` sets `package-lock=false`, and `.gitignore` excludes it), and Trivy reads dependency versions from lockfiles. We could not use `npm install` to make one.
- **Image scan:** 248 vulnerabilities and 4 secrets. By severity: 14 CRITICAL, 74 HIGH, 115 MEDIUM, 38 LOW, 7 UNKNOWN. By kind: 149 in Node packages and 99 in the Debian 13.4 base. The 4 secrets are the 3 from the source scan plus the same private key in the built `build/lib/insecurity.js`.
- **No Docker socket** was needed. Trivy pulled the image from the registry itself.
- **Dependency findings therefore come from the image scan.** `node_modules` is baked into the image.

### ZAP

- **Baseline scan result:** 0 failures, 8 warnings, 60 checks passed. The report lists 10 alert types: 2 Medium, 5 Low, 3 Informational. Examples: Content Security Policy (CSP) Header Not Set (plugin 10038, Medium), Cross-Domain Misconfiguration (10098, Medium).
- **Reached over the project network.** No host port was published for the target.
- **Can ZAP write SARIF directly? Yes, but not from `zap-baseline.py`.** The script only offers HTML (`-r`), Markdown (`-w`), XML (`-x`) and JSON (`-J`). SARIF comes from the Automation Framework `report` job with `template: sarif-json`. The plan is `spikes/S3/zap-sarif-plan.yaml` (about 25 lines) and it ran with `zap.sh -cmd -autorun`. It wrote a 212 KB file with 20 results. It is valid 2.1.0, tool `ZAP 2.17.0`.
- **Effort to convert:** none, if we use the plan. If we keep `zap-baseline.py`, we would convert its JSON ourselves, which is more work than switching to the plan.
- **Caveat:** SARIF locations are URLs (for example `http://juice-shop:3000`), not files. They cannot be matched to a line of source. That matters for fingerprints in M4-1.

### Key question: does Semgrep flag the login SQL injection?

**Yes.** Two rules fire on the same line. The vulnerable line is a template string that puts `req.body.email` straight into a `SELECT * FROM Users` query.

| | |
|---|---|
| File and line | `routes/login.ts:34` |
| Rule 1 | `javascript.express.security.injection.tainted-sql-string.tainted-sql-string` (ERROR) |
| Rule 2 | `javascript.sequelize.security.audit.sequelize-injection-express.express-sequelize-injection` (ERROR) |

Excerpt from `semgrep.sarif`:

```json
{"ruleId": "javascript.sequelize.security.audit.sequelize-injection-express.express-sequelize-injection",
 "locations": [{"physicalLocation": {"artifactLocation": {"uri": "/src/juice-shop/routes/login.ts"},
                "region": {"startLine": 34}}}]}
```

Both rules also fire on `routes/search.ts:23` (the product search). That gives us a second SQL injection at no extra cost.

One thing to design for in M2-5: two rule IDs on one line should become one ticket, so the fingerprint should use file, line and vulnerability class, not only the rule ID.

### SARIF excerpts from the other scanners

```json
// trivy-fs.sarif, tool Trivy 0.76.2
{"ruleId": "private-key", "level": "error",
 "locations": [{"physicalLocation": {"artifactLocation": {"uri": "lib/insecurity.ts"}, "region": {"startLine": 23}}}]}

// trivy-image.sarif
{"ruleId": "CVE-2015-9235", "level": "error",
 "locations": [{"physicalLocation": {"artifactLocation": {"uri": "juice-shop/node_modules/express-jwt/node_modules/jsonwebtoken/package.json"}, "region": {"startLine": 1}}}]}

// zap.sarif.json, tool ZAP 2.17.0
{"ruleId": "10038", "level": "warning",
 "locations": [{"physicalLocation": {"artifactLocation": {"uri": "http://juice-shop:3000"}, "region": {"startLine": 1}}}]}
```

### Proposed curated findings

Listed in the order we suggest using them.

| # | Finding | Tool and rule ID | File and line | Severity | Why it suits the demo |
|---|---|---|---|---|---|
| 1 | SQL injection in login | Semgrep `tainted-sql-string` (and `express-sequelize-injection`) | `routes/login.ts:34` | ERROR | The thin-slice finding. The exploit is one request that logs in without a password. The fix is small: use bound parameters instead of a template string. |
| 2 | SQL injection in product search | Semgrep `tainted-sql-string` (and `express-sequelize-injection`) | `routes/search.ts:23` | ERROR | Same class of flaw, so the fixer can reuse the lesson, and a UNION query gives a clear exploit. Small fix: bound parameters. |
| 3 | Hard-coded RSA private key | Trivy `private-key`; Semgrep `jwt-hardcode.hardcoded-jwt-secret` also flags the signing line at `lib/insecurity.ts:56` | `lib/insecurity.ts:23` | HIGH (Trivy) | Two scanners agree, which shows de-duplication. The exploit is forging a valid login token with the leaked key. The fix is to load the key from a file or environment variable. It touches a key the app and its challenges depend on, so check the effect in M4-3. |
| 4 | Vulnerable JWT library `jsonwebtoken` 0.4.0 | Trivy (image) `CVE-2015-9235` | `package.json:132` (pinned `0.4.0`) | CRITICAL | The one dependency finding. It is pinned exactly, so it still appears after a rebuild. Fixed in 4.2.2 or later. The exploit is a forged token accepted by the library. The code uses `jwt.sign`, `jwt.verify` and `jwt.decode` in three files. A major-version bump needs a test run, so this one is not as small as the others. |
| 5 | Content Security Policy header missing | ZAP baseline, plugin `10038` | whole site (no line) | Medium | The one DAST finding. The fix is small: add a CSP header in `server.ts`. Proof is a re-scan, not an exploit script, so it is optional. |

Alternates if one does not work out: open redirect (`javascript.express.security.audit.express-open-redirect`, `routes/redirect.ts:19`, WARNING), and the compression 1.8.1 patch bump (HIGH).

**Do not use `compression` or `body-parser` as the dependency finding.** Their ranges (`^1.8.1`, `^1.20.4`) already allow the fixed versions, and there is no lockfile. A fresh `npm install` during our image build would pick the fixed version and the finding would vanish on its own.

### Clean-up

`make clean-all` removed the stopped target container, the network, the three volumes and all five pulled images. Afterwards there were no labelled containers, volumes or networks, no spike image, and nothing listening on port 3000. The Rancher images (9) and its containers (28) were untouched.

Pulling by `tag@digest` leaves an image with no plain tag (`repo:<none>`). The first draft of the pulled-images list used plain tags and would have missed them. The list now uses the `repo:tag@sha256:…` form, and `clean-all` was proved against it.

## Cost

None. No paid call was made. The images and the Trivy database were downloaded for free.

## Decision

Go. All three scanners run in containers on this Mac and produce SARIF, with one workaround for ZAP.

- Use **Semgrep** for the thin slice (M2-4). It finds the login injection with two rules. Scan from the repo root with relative paths, and exclude `data/static/codefixes/` and `.github/` to cut the noise.
- Use **Trivy on the built image** for dependency findings, not Trivy on the source.
- Use ZAP through a short **Automation Framework plan** if we want SARIF from it.
- Take findings 1 to 4 as the curated set, and finding 5 if we want a DAST example. M4-3 confirms them.

## Surprises and risks

- **No lockfile means no dependency findings from source scans.** It affects M2-4 (keep it Semgrep only), M4-1 (dependency intake must read the image scan) and M4-3 (choose exactly-pinned dependencies).
- **Semgrep Rules License v1.0.** The rules are for internal business use only and may not be distributed or offered as a service. The repo is private and the demo is our own use, so this is fine now. Do not copy rule files into the repo. Rule IDs and result locations are what we keep. Before M6-5 (public repo or GitHub Pro) and the M6-6 recording, check that no rule text is published. This is a reading of the licence text, not legal advice. Affects `docs/HLD.md` if it names the rule sets.
- **ZAP SARIF locations are URLs, not source lines.** Affects M4-1 (fingerprints) and the evidence step in M2-8.
- **Two rule IDs on one line.** Affects M2-5 and M4-1 (de-duplication).
- **Memory.** ZAP (830 MiB) and Semgrep (626 MiB) are the big ones. Run scanners one at a time on the 4 GB Rancher VM. Affects M2-8 and M4-2 (the dispatcher runs three findings at a time, which is about fixers, not scanners).
- **Compose and digests.** Compose pulls by digest, so images have no plain tag. Every list or script that names an image should use `repo:tag@sha256:…`.
- **The `// vuln-code-snippet` comments in Juice Shop** label its own vulnerabilities. Scanners ignore them, but an AI fixer will see them. Affects M2-7.

## Follow-up

- M2-4: use Semgrep only, exclusions as above, relative paths, and de-duplicate by file, line and class.
- M4-1: note that dependency findings come from image scans, and that ZAP findings have URLs, not lines.
- Add a line to M4-3: curated dependency findings must be exactly pinned.
- M6-5 and M6-6: check the Semgrep Rules License before the repo goes public or the demo is recorded.
- No new tasks or spikes.
