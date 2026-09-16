#!/usr/bin/env bash
# =============================================================================
# CanBiomark.ai container entrypoint.
#
# Prepares the mounted data folder, checks that the pieces the application
# depends on are actually present, then starts the server. Every check fails
# loudly here rather than halfway through a three-hour simulation.
# =============================================================================
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
SHARED_INPUT_DIR="${SHARED_INPUT_DIR:-$DATA_DIR/catalogue}"
STAGING_DIR="${DATASET_IMPORT_STAGING_DIR:-$DATA_DIR/_imports}"
HTTP_PORT="${PORT:-8000}"

log() { printf '%s  %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S')" "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

# --- the mounted folder ------------------------------------------------------
prepare_data_directory() {
  mkdir -p "$DATA_DIR" "$SHARED_INPUT_DIR" "$STAGING_DIR" "$DATA_DIR/users"

  if [ ! -w "$DATA_DIR" ]; then
    fail "$DATA_DIR is not writable by uid $(id -u).
       The folder you mounted must be writable by the container user.
       Fix it on the host with:  chmod -R u+rwX <your folder>
       or run the container with:  --user \"\$(id -u):\$(id -g)\""
  fi
  log "Data directory ready at $DATA_DIR"
}

# --- dependency checks -------------------------------------------------------
check_environments() {
  local application_anndata conversion_anndata

  application_anndata="$(/opt/venv/bin/python -c 'import anndata; print(anndata.__version__)' 2>/dev/null || echo missing)"
  [ "$application_anndata" = "0.7.6" ] || fail \
    "The application environment has anndata '$application_anndata' but needs 0.7.6.
       SeuratDisk cannot read what any other version writes, which breaks SimBu."

  conversion_anndata="$(/opt/venv-conversion/bin/python -c 'import anndata; print(anndata.__version__)' 2>/dev/null || echo missing)"
  [ "$conversion_anndata" != "missing" ] || fail \
    "The dataset conversion environment is missing. Dataset import would fail."

  log "Python: application anndata $application_anndata, conversion anndata $conversion_anndata"

  command -v Rscript >/dev/null 2>&1 || fail "Rscript is not on PATH; SimBu cannot run."
  Rscript -e 'quit(status = !all(c("Seurat","SeuratDisk","SimBu") %in% rownames(installed.packages())))' \
    >/dev/null 2>&1 || fail "Seurat, SeuratDisk or SimBu is missing from the R library."
  log "R: Seurat, SeuratDisk and SimBu are present"

  command -v java >/dev/null 2>&1 || fail "Java is not on PATH; the H2O AI suite cannot start."
  log "Java: $(java -version 2>&1 | head -1)"

  [ -f "${SIMBU_R_SCRIPT:-/app/backend/app/scripts/simbu.R}" ] \
    || fail "The SimBu R script is missing at ${SIMBU_R_SCRIPT:-}."
}

# --- first-run guidance ------------------------------------------------------
report_catalogue_state() {
  local dataset_count
  dataset_count="$(find "$SHARED_INPUT_DIR" -maxdepth 1 -name 'combined_adata_*.h5ad' 2>/dev/null | wc -l | tr -d ' ')"

  if [ "$dataset_count" = "0" ]; then
    log "The shared catalogue at $SHARED_INPUT_DIR is empty."
    log "  Sign in as an administrator and use 'Datasets' to import one,"
    log "  or copy your own pair of files into it:"
    log "    combined_adata_<name>.h5ad   and   catalog_<name>.txt"
    log "  where catalog_<name>.txt holds one line:  <experiment>;<tissue label>"
  else
    log "Shared catalogue: $dataset_count dataset(s) available"
  fi
}

warn_about_admin_password() {
  if [ -z "${ADMIN_PASSWORD:-}" ]; then
    log "ADMIN_PASSWORD is not set: a random one will be generated and printed"
    log "  below, once. Copy it, sign in, and change it."
  fi
}

# --- commands ----------------------------------------------------------------
case "${1:-serve}" in
  serve)
    log "Starting CanBiomark.ai"
    prepare_data_directory
    check_environments
    warn_about_admin_password
    report_catalogue_state
    log "Listening on port $HTTP_PORT"
    cd /app/backend
    exec /opt/venv/bin/python -m uvicorn app.main:app \
        --host 0.0.0.0 --port "$HTTP_PORT" --proxy-headers
    ;;

  check)
    # Verify the image without starting the server.
    prepare_data_directory
    check_environments
    report_catalogue_state
    log "All checks passed."
    ;;

  shell)
    exec /bin/bash
    ;;

  *)
    # Anything else runs verbatim, e.g. docker run ... python -m pytest
    exec "$@"
    ;;
esac
