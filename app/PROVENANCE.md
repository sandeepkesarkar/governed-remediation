# Provenance of `app/`

This folder holds the vendored source of OWASP Juice Shop. It is a deliberately vulnerable app. Do not fix it by hand. Fixing it is the job of the fixer agent.

| | |
|---|---|
| Upstream | https://github.com/juice-shop/juice-shop |
| Tag | `v20.0.0` |
| Commit SHA | `f356a09207c7a9550eb6fc4c3945e081922cf998` (the commit the tag points to) |
| Tag object | `2cc9ac8d32ee7ddd2c39362daac767527ec84640` (annotated tag) |
| Vendored on | 2026-11-18 |
| Local changes | None to any kept file. Excluded paths are listed below. |

## How it was taken

A shallow clone of the tag, made in a container (`alpine/git`, pinned in `docs/ENVIRONMENT.md`). The commit SHA was checked against `git ls-remote` on the upstream URL (the peeled tag `v20.0.0^{}`). Then the tree was copied here without the excluded paths.

## What was excluded

- `.git/` (the upstream history)
- `.github/` (upstream workflows and issue templates)
- **AI-assistant instruction files** (removed after the first vendoring, 2026-11-18):
  - `AGENTS.md`
  - `.claude/` (`CLAUDE.md` and its `.gitignore`)
  - `.cursor/` (`rules`)
  - `.codeium/` (`instructions.md`)
  - `.continue/` (`instructions.md`)
  - `.junie/` (`AGENTS.md`, `config.json`)
  - `.ai/` (the `skills/` folder, 22 files)

  Reason: third-party agent instructions are not part of the running app, and they could steer our agents. **A re-vendor must exclude them again**, and must search for any new file of this kind (for example `GEMINI.md`, `.windsurf`, `.github/copilot-instructions.md`). A search of the v20.0.0 tree found no others. `.gitattributes` and `.gitignore` still mention some of these paths. They are configuration, not instructions, and are left as upstream has them.

Upstream has no `node_modules`, no build output and no lockfile in the tag. The tag has 1,235 files, about 48 MB. After removing the instruction files, 1,205 upstream files remain. The largest file is `frontend/src/assets/public/videos/owasp_promo.mp4`, about 10 MB.

## Things to know

- **Upstream `.gitignore` is kept.** Nine files under `frontend/src/assets/private/` (the `*.js` files) and `ftp/encrypt.pyc` match an ignore pattern. They were added with `git add -f`. If you re-vendor, do the same, and check that the tracked count is 1,205 upstream files plus this note.
- **The build.** The Dockerfile is upstream's, unchanged. It uses the base images `node:24` and `gcr.io/distroless/nodejs24-debian13`, which are pinned by digest from the `Makefile` (see `docs/ENVIRONMENT.md`).

## Fake keys and secrets

Juice Shop ships intentionally fake keys and secrets so that its challenges work. A secrets scan will find them. The pre-publication secrets scan needs a documented allowlist for `app/`. These are the places found:

| Path | What it is |
|---|---|
| `lib/insecurity.ts` | A hard-coded RSA private key and a signing secret, used by the challenges |
| `encryptionkeys/jwt.pub` | The public key that matches the key above |
| `encryptionkeys/premium.key` | A key for a challenge |
| `ctf.key` | A key file for the CTF mode |
| `ftp/package-lock.json.bak` | A lockfile left in the downloadable `ftp` folder, kept for a challenge |

This list is from a search for private key headers and for key files by name. It is not a full scan. The path allowlist for these files is in `.gitleaks.toml` at the repo root, used by `make scan-secrets`.

### Allowlisted scan findings (owner decision, 2026-11-18)

The secrets scan (`make scan-secrets`) also reports 58 findings in 20 other files. They are upstream's own sample data, source for its challenges, and tests. The reason for every group below is the same: **Juice Shop's own tests and sample data, public upstream.** None of the values is a credential for any real system, as far as the code shows; the tests need them. The tests stay in `app/` because the verify step (M2-8) runs them.

Each file is allowlisted by exact path (no folder patterns, no line numbers, because the fixer's edits move lines), and each entry is scoped to the rule IDs that fired there. A new finding of any other rule in the same file still fails the scan. When a re-vendor changes these files, run the scan and review any new finding before allowlisting it.

**Source and sample data** (not tests):

| Path | Rule and count |
|---|---|
| `data/static/users.yml` | `generic-api-key` x2 |
| `frontend/src/app/faucet/faucet.component.ts` | `generic-api-key` x1 |
| `routes/login.ts` | `generic-api-key` x1 |

- `data/static/users.yml`: sample user records that seed the demo shop (passwords of fake users).
- `frontend/src/app/faucet/faucet.component.ts`: a public blockchain contract address for the web3 challenge. Not a secret.
- `routes/login.ts`: one hard-coded check for the OAuth user challenge. The password is stored base64-encoded on purpose, so players can find it. It belongs to a challenge user of the demo shop. It is public in upstream.

**Tests** (upstream's own unit, API and end-to-end tests):

| Path | Rule and count |
|---|---|
| `frontend/src/app/app.guard.spec.ts` | `jwt` x1 |
| `frontend/src/app/last-login-ip/last-login-ip.component.spec.ts` | `generic-api-key` x1, `jwt` x1 |
| `frontend/src/app/oauth/oauth.component.spec.ts` | `generic-api-key` x3 |
| `test/api/2fa.test.ts` | `generic-api-key` x12 |
| `test/api/basket.test.ts` | `generic-api-key` x1 |
| `test/api/data-export.test.ts` | `generic-api-key` x3 |
| `test/api/erasure-request.test.ts` | `generic-api-key` x6 |
| `test/api/feedback.test.ts` | `generic-api-key` x2 |
| `test/api/login.test.ts` | `generic-api-key` x3 |
| `test/api/product-review.test.ts` | `generic-api-key` x2 |
| `test/api/user.test.ts` | `generic-api-key` x5, `jwt` x1 |
| `test/api/web3.test.ts` | `generic-api-key` x3 |
| `test/cypress/e2e/forgedJwt.spec.ts` | `jwt` x2 |
| `test/cypress/e2e/login.spec.ts` | `generic-api-key` x1 |
| `test/cypress/e2e/totpSetup.spec.ts` | `generic-api-key` x1 |
| `test/server/currentUserSpec.ts` | `jwt` x2 |
| `test/server/verifySpec.ts` | `jwt` x4 |
 Do not treat anything under `app/` as a real secret, and do not put a real secret there.

## Licences

- Juice Shop: MIT, `app/LICENSE`, Copyright (c) 2014-2026 Bjoern Kimminich and the OWASP Juice Shop contributors. This is the only licence file in the tree.
- Third-party code: `frontend/src/assets/private/` holds `three.js`, `OrbitControls.js`, `EffectComposer.js`, `MaskPass.js`, `RenderPass.js`, `ShaderPass.js`, `CopyShader.js`, `stats.min.js` and `dat.gui.min.js`. Their headers name authors (for example mrdoob, alteredq, qiao) and do not state a licence. No licence is recorded here, because none was found in the files. It is not guessed. **Decision (owner, 2026-11-18): keep these nine files exactly as upstream ships them.** Do not edit them.
- Upstream's `README.md` says that the book "Pwning OWASP Juice Shop" is published under CC BY-NC-ND 4.0. The book is not in this tree.
- Images, fonts and videos under `frontend/src/assets/` have no licence statement in the tree. None is recorded here.
- Package dependencies are installed at build time. Their licences are not part of this tree.
