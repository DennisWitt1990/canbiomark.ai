# =============================================================================
# CanBiomark.ai - single image containing every part of the application
#
#   * R 4.3.3 with Seurat, SeuratDisk and SimBu, at the pinned commits
#   * Python 3 with anndata 0.7.6 for the application (SimBu compatibility)
#   * a SECOND Python environment with a modern anndata, used only to convert
#     downloaded datasets (0.7.6 cannot read what modern anndata writes)
#   * a Java runtime for the H2O cluster used by the AI suite
#   * the built React frontend, served by the backend from the same origin
#
# Everything a user must supply is one folder, mounted at /data.
# =============================================================================

###############################################################################
# STAGE 0: build the frontend bundle
###############################################################################
FROM node:22-slim AS frontend-builder
WORKDIR /build/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
# No VITE_API_URL: the bundle talks to the backend on its own origin.
RUN npm run build


###############################################################################
# STAGE 1: runtime
###############################################################################
FROM rocker/r-ver:4.3.3

LABEL org.opencontainers.image.title="CanBiomark.ai" \
      org.opencontainers.image.description="Synthetic bulk RNA-seq generation and benchmarking" \
      org.opencontainers.image.version="2.1.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- system packages ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip python3-dev \
      build-essential pkg-config gfortran \
      libopenblas-dev liblapack-dev \
      libhdf5-dev hdf5-tools \
      default-jre-headless \
      libcurl4-openssl-dev libssl-dev libxml2-dev \
      libffi-dev libbz2-dev liblzma-dev \
      libglpk-dev libgmp3-dev \
      libpng-dev libjpeg-dev libtiff5-dev \
      libfreetype6-dev libharfbuzz-dev libfribidi-dev \
      libxt6 patch wget curl git ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

# --- R packages, pinned to the commits SimBu is known to work with -----------
# Slowest layer by far; kept before any application code so it is cached.
ENV R_LIBS_SITE=/usr/local/lib/R/site-library
RUN R -q -e "options(repos=c(CRAN='https://cloud.r-project.org')); install.packages('remotes')" \
 && R -q -e "remotes::install_version('Seurat', version=package_version('5.0.3'), upgrade='never')" \
 && R -q -e "remotes::install_github('mojaveazure/seurat-disk@877d4e18ab38c686f5db54f8cd290274ccdbe295', upgrade='never')" \
 && R -q -e "remotes::install_github('omnideconv/SimBu@cdaf4292002f8df2124f0703a743af16e12900e6', upgrade='never')" \
 && R -q -e "stopifnot(requireNamespace('Seurat', quietly=TRUE), requireNamespace('SeuratDisk', quietly=TRUE), requireNamespace('SimBu', quietly=TRUE))"

# --- environment 1: the application, pinned to anndata 0.7.6 -----------------
COPY backend/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
 && /opt/venv/bin/python -c "\
import anndata, sys; \
version = anndata.__version__; \
sys.exit(0) if version == '0.7.6' else sys.exit( \
  f'FATAL: anndata {version} was installed but 0.7.6 is required. ' \
  'SeuratDisk cannot read what any other version writes, which breaks SimBu.')"

# --- environment 2: dataset conversion only, modern anndata ------------------
COPY backend/requirements-conversion.txt /tmp/requirements-conversion.txt
RUN python3 -m venv /opt/venv-conversion \
 && /opt/venv-conversion/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
 && /opt/venv-conversion/bin/pip install --no-cache-dir -r /tmp/requirements-conversion.txt \
 && /opt/venv-conversion/bin/python -c "\
import anndata; \
assert anndata.__version__ >= '0.10', anndata.__version__; \
print('conversion environment: anndata', anndata.__version__)"

# --- application code --------------------------------------------------------
WORKDIR /app
COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# --- defaults ----------------------------------------------------------------
# Everything the user cares about lives under /data, the single mount point.
ENV PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data \
    SHARED_INPUT_DIR=/data/catalogue \
    DB_PATH=/data/canbiomark.sqlite \
    DATASET_IMPORT_STAGING_DIR=/data/_imports \
    DATASET_CONVERSION_PYTHON=/opt/venv-conversion/bin/python \
    SIMBU_R_SCRIPT=/app/backend/app/scripts/simbu.R \
    FRONTEND_DIST=/app/frontend/dist \
    SERVE_FRONTEND=1 \
    H2O_MAX_MEMORY=20g \
    LOG_LEVEL=INFO

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1

# tini reaps the R and Java child processes that SimBu and H2O leave behind.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["serve"]
