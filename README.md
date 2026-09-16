# CanBiomark.ai

CanBiomark.ai is a web application for generating labelled synthetic bulk
RNA-seq tissues from single-cell references using SimBu. Researchers can inspect
and import references, select annotated cell populations, configure mixture
fractions, run batches and download the resulting expression datasets for
downstream analysis and model development.

The application combines a React interface, a Python API and an R simulation
workflow, with user workspaces and an administrator-managed reference catalogue.
Additional tissue combinations can be generated; their biological validity and
predictive utility need to be assessed for each research application.

## Getting started

From the root of this source directory:

```bash
cd docker
cp .env.example .env
# Edit .env to set the administrator password and data directory.
docker compose up --build
```

Open `http://localhost:8000`. See [SETUP.md](SETUP.md) for memory requirements,
configuration, reference import and deployment instructions. Reference datasets,
clinical data and local accounts are not included in the source distribution.

## Research use and availability

The accompanying manuscript evaluates synthetic training for lymphocyte-related
prediction. Its PyTorch recomputation workflow is maintained separately from
the application's built-in analysis modules. Generating a synthetic dataset
does not by itself validate a downstream biomarker or clinical decision rule.

Maintained by Dennis Witt at
[DennisWitt1990/canbiomark.ai](https://github.com/DennisWitt1990/canbiomark.ai).
A release citation will be added with the accompanying publication.
No software licence has yet been specified; public source access alone does
not grant a licence. Dataset access and reuse remain subject to the conditions
of each original source.

## Implementation notes

The following sections document the current refactored implementation,
including account management and the changes from the earlier application.

---

## What changed, and why

### 1. Authentication: passwords in SQLite instead of bearer tokens

| Before | Now |
| --- | --- |
| An admin generated an invite code; redeeming it created an anonymous UUID account and returned a long-lived bearer token. | An administrator creates a named account. The user signs in with **username + password**. |
| The token never expired and could not be revoked per user. | Sessions expire (12 h by default) and can be revoked individually or per user, taking effect on the very next request. |
| `ADMIN_TOKEN` was a single shared secret in an environment variable. | Administrator is a **role on a real account**, so actions are attributable and there is an audit trail. |
| Tokens hashed with `sha256(token + pepper)`. | Passwords hashed with **PBKDF2-HMAC-SHA256**, 240 000 iterations, a fresh 16-byte salt per user, stored with their cost factor so it can be raised later. |

No new dependency was needed: PBKDF2 ships with the Python standard library.

Security properties, all covered by tests:

- The password is never stored, logged or returned — only its salted hash.
- A wrong username and a wrong password give the **same** message and cost
  roughly the same time, so the endpoint does not disclose which accounts exist.
- The session cookie is `HttpOnly` + `SameSite=Lax`; only the SHA-256 of the
  token is in the database, so a database leak hands out no usable cookies.
- Disabling an account or resetting its password revokes its sessions at once.
- Changing your own password signs you out everywhere.
- The server refuses any change that would leave no active administrator, so
  the installation cannot be locked out.

### 2. The administrator has a real user interface

Under **User administration** an administrator can, without touching a terminal:

- see every account with its role, status, disk usage against quota, session
  count and last sign-in;
- create an account, with a generated or hand-picked initial password shown
  **once** with a copy button;
- change display name, role, quota and the active flag;
- reset a password (issues a new one, ends all sessions);
- list active sessions and sign a user out everywhere;
- delete an account together with its workspace, behind a confirmation dialog;
- read the audit trail of sign-ins, failed attempts and administrative changes.

### 3. Object-oriented structure throughout

The old code mixed HTTP handling, SQL, file paths and science in the same
functions, with module-level globals and `os.getenv` calls scattered around.
Now each concern is a class with one job, wired by constructor injection in a
single composition root (`app/container.py`):

```
api/routers/*   HTTP only: parse the request, call a service, shape the response
services/*      the use cases; no FastAPI import anywhere in this layer
domain/*        plain objects with behaviour (UserAccount, SimBuParameters, ...)
database/*      the only place that writes SQL
security/*      password hashing, policy, session tokens
jobs/*          thread-safe registry + worker for long-running work
config/         the only place that reads os.environ
```

Same idea in the frontend: `HttpClient` is the single HTTP entry point, one
API class per area, domain classes (`CurrentUser`, `ManagedUser`, `BatchJob`)
that carry their own logic. React components stay functions, which is the
idiomatic form — class components have been legacy React for years — so the
object orientation sits in the layers underneath them.

### 4. Clear names

Every abbreviation is spelled out: `exp_indices` → `experiment_ids`,
`cts` → `cell_types`, `sel_celltypes` → `selected_cell_types`, `thr` →
`threshold`, `p` → `completed_process`, `_set_job` → `JobRegistry.update`.
Modules are named after what they do, not numbered: `module3` →
`cell_selection`, `module4` → `tissue_generator`, `module4_batch` →
`tissue_batches`, `module5` → `ai_suite`.

### 5. Bugs found and fixed on the way

- **`module5.py` threshold list.** It read
  `[0.01, 0,.02, 0.03, ...]` — a stray comma that silently made it
  `[0.01, 0, 0.02, ...]`. The extra `0` threshold binarises every label to 1,
  which either crashes H2O with "response cannot be constant" or trains a
  meaningless model. Now `[0.01, 0.02, 0.03, ...]` as intended.
- **Path handling.** `/etc/passwd` used to be silently rewritten to
  `<workspace>/etc/passwd`. Contained, but it hid caller bugs; absolute paths
  are now rejected outright. One download endpoint replaces the four
  near-identical per-module copies.
- **Dead code removed.** `core Kopie.py`, `module4 Kopie.py`,
  `module5 Kopie.py`, and `INVESTIGATOR.py` (which hard-coded
  `/Users/jannawitt/...`).
- **Transactions.** Several write paths could leave the database half-updated
  on an error; all writes now go through one commit/rollback context manager.
- **Silent `except: pass` blocks** replaced with logging or real handling.

### 6. Deliberately kept

- **`anndata==0.7.6`.** Non-negotiable: the pinned SeuratDisk commit can only
  read the h5ad layout this version writes. The Dockerfile now *verifies* the
  installed version at build time and fails loudly instead of producing an
  image that breaks at the SimBu step.
- The batch runner's shared-input optimisation (one copy per dataset per job,
  cached h5seurat conversion) — it is the difference between ~20 GB and
  ~550 GB of scratch space on a 50-task batch.
- The skipped-threshold reporting in the AI suite, which records constant-label
  thresholds in their own Excel sheet rather than dropping them silently.

---

## Layout

```
canbiomark.ai_refactored/
├── backend/
│   ├── app/
│   │   ├── main.py                 ASGI entry point
│   │   ├── application.py          ApplicationFactory: builds and wires the app
│   │   ├── container.py            composition root; every service built once
│   │   ├── config/settings.py      the only reader of os.environ
│   │   ├── domain/                 UserAccount, LoginSession, SimBuParameters, ...
│   │   ├── security/               PasswordHasher, PasswordPolicy, SessionTokenFactory
│   │   ├── database/               connection, schema, repositories
│   │   ├── services/               the use cases
│   │   ├── jobs/                   JobRegistry, BackgroundWorker
│   │   ├── api/                    dependencies, schemas, routers, error handlers
│   │   └── scripts/simbu.R         unchanged SimBu driver
│   ├── tests/                      114 tests
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/                    HttpClient + one API class per area
│       ├── context/                AuthenticationContext
│       ├── components/             Button, Card, TextField, dialogs, layout
│       └── pages/                  admin/, cellselection/, tissue/, aisuite/
└── docker/                         Dockerfile + docker-compose.yml
```

---

## Running it

**See [SETUP.md](SETUP.md) for the full installation guide.** The short version:

```bash
cd docker
cp .env.example .env          # set CANBIOMARK_DATA_DIR and ADMIN_PASSWORD
docker compose up -d --build  # the first build takes 45-90 minutes
```

Then open <http://localhost:8000>. Everything lives in the one folder you point
`CANBIOMARK_DATA_DIR` at: the database, every user's workspace and the shared
dataset catalogue.

The image carries R with Seurat/SeuratDisk/SimBu at their pinned commits, the
Java runtime H2O needs, the built frontend, and **two** Python environments —
see below.

### Why the image has two Python environments

The application is pinned to `anndata==0.7.6`, because the SeuratDisk commit
SimBu depends on can only read what that version writes. But 0.7.6 also cannot
*read* what modern anndata writes, and every dataset published by CELLxGENE or
EBI was written by a modern version. The predecessor downloader documents the
same split: run the conversion "in a MODERN anndata env; the result is then
read by your SimBu env".

So the image ships:

| Environment | anndata | Used for |
|---|---|---|
| `/opt/venv` | pinned `0.7.6` | the whole application, including everything SimBu reads |
| `/opt/venv-conversion` | `>=0.10` | only `app/tools/convert_dataset.py`, invoked as a subprocess |

`DATASET_CONVERSION_PYTHON` points the import service at the second one. Left
unset — as on a development machine that already has a modern anndata — the
conversion runs in-process instead. Both paths are covered by tests, and the
build fails loudly if the application environment ends up on anything but
0.7.6.

### Local development

```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=./_data ADMIN_PASSWORD='dev-password-123' \
  python -m uvicorn app.main:app --reload --port 8000

# frontend, in a second terminal
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

The tests need only FastAPI and pytest — the services import scanpy, h2o and
matplotlib lazily, so the suite runs in a couple of seconds without the
scientific stack installed. The handful that exercise the conversion tool skip
themselves unless a modern anndata is present.

```bash
cd frontend
npm run typecheck                   # tsc --noEmit, clean
npm run build
```

---

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATA_DIR` | `/app/data` | Root for the database and all user workspaces. |
| `DB_PATH` | `$DATA_DIR/canbiomark.sqlite` | SQLite file. |
| `SHARED_INPUT_DIR` | `$DATA_DIR` | Where the experiment catalogue (`*.txt` + `combined_adata_*.h5ad`) lives. |
| `ADMIN_USERNAME` | `admin` | Bootstrap administrator, created only when no active administrator exists. |
| `ADMIN_PASSWORD` | *(empty)* | Its password. Empty ⇒ generated and logged once. |
| `SESSION_COOKIE_SECURE` | `0` | **Set to `1` behind HTTPS.** |
| `SESSION_LIFETIME_HOURS` | `12` | How long a session stays valid. |
| `PASSWORD_HASH_ITERATIONS` | `240000` | PBKDF2 cost. Raising it re-hashes each password at its owner's next sign-in. |
| `MINIMUM_PASSWORD_LENGTH` | `10` | Password policy. |
| `DEFAULT_QUOTA_GB` | `50` | Quota for new accounts. |
| `SIMBU_R_SCRIPT` | `app/scripts/simbu.R` | Path to the SimBu driver. |
| `SIMBU_TIMEOUT_SECONDS` | `3600` | Per-simulation timeout. |
| `H2O_MAX_MEMORY` | `20g` | Heap for the AI suite. |
| `SERVE_FRONTEND` | `0` | Serve the built bundle from the backend origin. |
| `ALLOWED_ORIGINS` | *(empty)* | Extra CORS origins; localhost is always allowed. |

---

## API

All endpoints live under `/api`. Everything except `/api/health` and
`/api/auth/login` requires the session cookie.

| Area | Endpoints |
| --- | --- |
| Authentication | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password`, `GET /auth/password-policy` |
| Administration | `GET/POST /admin/users`, `PATCH/DELETE /admin/users/{id}`, `POST /admin/users/{id}/password`, `GET/DELETE /admin/users/{id}/sessions`, `GET /admin/audit` |
| Workspace | `GET /workspace/download`, `GET /workspace/files` |
| Cell selection | `GET /cell-selection/experiments`, `POST /cell-selection/merge`, `POST /cell-selection/filter` |
| Tissue generator | `POST /tissue-generator/upload`, `POST /tissue-generator/run` |
| Tissue batches | `POST /tissue-batches/definitions`, `GET/POST /tissue-batches/jobs`, `GET/DELETE /tissue-batches/jobs/{id}`, `GET /tissue-batches/jobs/{id}/archive` |
| AI suite | `GET/POST /ai-suite/jobs`, `POST /ai-suite/jobs/{id}/uploads`, `POST /ai-suite/jobs/{id}/run`, `GET /ai-suite/jobs/{id}`, `GET /ai-suite/jobs/{id}/results` |

Interactive documentation is at `/docs` while the server runs.

---

## Migrating from the old installation

There is no automatic migration, by design: the old `users` table holds only
anonymous UUIDs with no username and no password, so there is nothing to carry
over that a person could sign in with. Recreate the accounts through the
administration screen and hand out the initial passwords.

Existing **workspace data** can be moved over — copy
`<old DATA_DIR>/users/<uuid>/` into `<new DATA_DIR>/users/<new uuid>/`, taking
the new UUID from the user list. The per-module subfolders were renamed:

| Old | New |
| --- | --- |
| `core/` | `cell_selection/` |
| `module4/uploads/` | `tissue_generator/uploads/` |
| `module4/<run id>/` | `tissue_generator/runs/<run id>/` |
| `module4_batch/` | `tissue_generator/batches/` |
| `module5/` | `ai_suite/` |

---

## Version 2.1 — regression, dataset import, cell type selection

### 1. Regression in the AI suite

The AI suite now offers two tasks over the same uploads:

| | Classification | Regression |
|---|---|---|
| Question | "Is the infiltration above 2 %?" | "How much infiltration is there?" |
| Models | Deep learning, one per threshold | Deep learning, GLM, gradient boosting, random forest |
| Metrics | AUC, sensitivity, specificity, F1 | MSE, RMSE, MAE, R² |
| Plots | ROC per threshold | Actual versus predicted per model |
| Output | `results_classification.xlsx` | `results_regression.xlsx` + a `Predictions` sheet with per-sample deltas |

Ported from the runnable implementation in the predecessor pipeline
(`MA_Extension/app/backend/app/ml/train.py::run_regression`) rather than from
the thesis appendix `supplement_F_regression_h2o.py`, which is a PDF extraction
and does not execute (syntax errors, `winsound`, placeholder paths). The metric
column names are kept identical so older result files stay comparable. Models
are seeded, and deep learning runs with `reproducible=True`, so two runs on the
same data agree.

**Two H2O bugs fixed along the way**, both documented from production runs of
the predecessor and both present in version 2.0 of this rewrite:

- `h2o.shutdown()` returns before the JVM releases the port, so the *next*
  job's `h2o.init()` attaches to a dying cluster and fails with
  `Connection refused`. `H2OSession.start()` now retries with a real REST round
  trip, and `stop()` waits for the port to be free.
- Python's `del` frees only the client handle; the frame stays in the JVM heap.
  Left alone the heap fills until the cluster thrashes — measured previously as
  one threshold taking over two hours instead of nine minutes.
  `H2OSession.release()` removes objects from the cluster itself.

### 2. Dataset import with a guided search

Administrators can find datasets online and publish them to the shared
catalogue, under **Datasets**. Researchers see the results in the cell selector
but cannot import — an import writes into the folder everyone reads from.

Two sources, chosen after testing both:

- **CELLxGENE Discover** for browsing: 390 collections whose per-dataset
  ontology labels (tissue, organism, assay, disease) map straight onto the
  filters, and whose `dataset_version_id` resolves to a downloadable `.h5ad`.
- **EBI BioStudies** for a known accession such as `E-MTAB-10553`. Its
  free-text search is deliberately *not* offered: a query for "single cell
  liver" returns over 900 000 hits, nearly all of them publications rather than
  datasets. The endpoint says so rather than returning noise.

The pipeline is download → inspect → **pause for confirmation** → convert →
verify → publish, running in the background with progress. The result lands as
`combined_adata_<name>.h5ad` plus a matching `catalog_<name>.txt`, which is the
format the cell selector already reads.

Conversion reuses the proven anndata 0.7.6 hardening path from
`weiterer Code/NewDownloaderANDConverter/fetch_biostudies_h5ad.py`
(`sanitize` → write → `harden` → `verify`), plus the CELLxGENE handling from
`pipeline/fetch_cellxgene.py` (raw counts out of `.raw.X`, HGNC symbols out of
`var.feature_name`). Verification emulates the 0.7.6 reader in pure `h5py`, so
it runs anywhere. Every imported file records its provenance in
`obs.source_dataset` and `obs.source_cell_type_column`.

### 3. Context-sensitive cell type column selection

The importer proposes a column and **always shows the alternatives**, because
picking the wrong one does not fail loudly — it produces simulations that run
perfectly and mean nothing.

Two corrections to the obvious design, both found on real files:

- **The preview shows the most frequent values, not the first rows.** In
  `E-HCAD-10_ad076.h5ad` the first three cells are all blank (21.9 % of the
  column is empty), so a raw `head()` would show three empty strings.
- **Two candidate columns from the predecessor's list were dropped.**
  `Factor Value[single cell identifier]` holds cell barcodes — in
  `E-MTAB-2983_ad076.h5ad` its values are `24`, `5`, `27`, which would have
  produced 38 meaningless "cell types" — and `Sample Characteristic[sampling
  site]` is a tissue. Both would have annotated confidently and wrongly.

Each candidate is scored and shown with its distinct count, missing fraction,
most frequent values and the reasons behind its score. Columns that are ruled
out are listed separately with the reason. Verified behaviour on real data:

| Dataset | Result |
|---|---|
| `combined_adata_2a.h5ad` | recommends `cell_type`; rejects the constant `tissue` and `file_name` |
| `E-HCAD-10_ad076.h5ad` | ranks *both* valid columns nearly level (ontology: 29 labels, authors: 44) so the user decides |
| `E-MTAB-2983_ad076.h5ad` | recommends **nothing** — the dataset genuinely has no cell type annotation |
| CELLxGENE "HVS" | recommends the constant `cell_type` with a warning, and offers `Supertype` (VLMC_1/VLMC_2) |

That last case fixed two scoring bugs: a dataset containing a *single* cell
type is legitimate, so a constant column is flagged rather than rejected; and a
known cell type name now always outranks an unrelated one, after an unrelated
`Age at death` column won a tie on ordering alone.

### Also fixed

Every domain enum (`UserRole`, `AnalysisTask`, `RegressionModelKind`,
`DatasetSource`) raised a bare `ValueError` on an unknown value, which escaped
as an opaque **500**. They now raise `ValidationError`, so a bad role or task
gives a **400** naming the offending value and the valid ones. This was a
pre-existing bug in the role endpoint, not only in the new code.

### Configuration added

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATASET_IMPORT_STAGING_DIR` | `$DATA_DIR/_imports` | Scratch space for downloads; cleared of orphans at start-up. |
| `MAX_DATASET_DOWNLOAD_GB` | `25` | Refuses larger downloads, before and during transfer. |
| `TLS_CA_BUNDLE` | *(empty)* | Explicit CA bundle. Otherwise `certifi` is used, which is what makes HTTPS work on macOS. |
| `ALLOW_INSECURE_DOWNLOADS` | `0` | Disables TLS verification. Logs a warning on every use; for a broken host only. |

### End-to-end verification

A real import was run against CELLxGENE: a 53.7 MB dataset downloaded,
inspected (637 cells × 18 736 genes), paused for the column decision,
`Supertype` confirmed, converted, verified as 0.7.6-readable and published as
`combined_adata_hvs_demo.h5ad` — which then appeared in the cell selector for a
researcher account, while that account received 403 on every import endpoint.

### Still open

- **Quotas remain unenforced**, and this now matters more: an administrator can
  fill the shared volume with imports. `MAX_DATASET_DOWNLOAD_GB` caps a single
  file but not the total.
- **Job state is still in memory.** A restart during an import discards the
  partial download (the staging folder is cleaned automatically) but loses the
  job's history.
- **No cell type harmonisation yet.** `MA_Extension/app/backend/app/celltype_map.py`
  and its 117-entry curated table map labels onto
  `LYMPHOCYTE` / `NONLYMPH` / `UNKNOWN`. Imported datasets keep their original
  labels; wiring that mapping in would be the natural next step.

---

## Known gaps

- **Quotas are reported, not enforced.** The administration screen shows usage
  against the quota, but no upload is rejected for exceeding it. Enforcing it
  belongs in `WorkspaceService` at the write path.
- **Jobs live in memory.** Batch and AI-suite job state is held in a registry
  inside the process, exactly as before, so a restart loses the *status* of a
  running job (files already written survive). Persisting the registry to
  SQLite would be the natural next step.
- **The old `Module2_Stratificator` page was not carried over.** It drove a
  Docker container over `/api/module2` WebSockets — an endpoint that does not
  exist anywhere in the original backend either, so the page could never have
  worked as shipped. It was left out rather than ported blind; say the word and
  it can be reinstated once the intended backend is available.
- **Rate limiting.** Failed sign-ins are recorded in the audit trail but not
  throttled. A reverse proxy or a lockout after N failures would close that.
