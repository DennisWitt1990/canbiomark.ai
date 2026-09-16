# This script imports the sc object created with simbu.py, and creates the simulated bulk data using SimBu

suppressPackageStartupMessages({
  library(Seurat)
  library(SeuratDisk)
  library(SimBu)
})

args <- commandArgs(trailingOnly = TRUE)

# Arguments (with sane defaults)
immune_cell_fraction <- if (length(args) >= 1 && nzchar(args[1])) as.numeric(args[1]) else 20
n_samples            <- if (length(args) >= 2 && nzchar(args[2])) as.integer(args[2]) else 50

if (is.na(immune_cell_fraction) || immune_cell_fraction < 0 || immune_cell_fraction > 99) {
  stop("immune_cell_fraction must be numeric in [0, 99]")
}
if (is.na(n_samples) || n_samples < 1) {
  stop("n_samples must be integer >= 1")
}

# Base path + sample name via ENV (fallbacks)
base_path   <- Sys.getenv("SIMBU_BASE_PATH",  unset = "/app/data/")
name_sample <- Sys.getenv("SIMBU_SAMPLE_NAME", unset = "final_mod_daten")

# NEW: Optional separate output directory.
# - If SIMBU_OUTPUT_DIR is set, PDFs/TXTs go there (under tissues/).
# - If not set, falls back to old behavior: <base_path>/tissues/ .
# This allows the batch runner to share base_path (h5ad + cached h5seurat)
# across many tasks while still writing per-task outputs to separate dirs.
output_root <- Sys.getenv("SIMBU_OUTPUT_DIR", unset = "")

# Normalize base_path: ensure trailing slash
if (!grepl("/$", base_path)) base_path <- paste0(base_path, "/")

in_h5ad   <- paste0(base_path, name_sample, ".h5ad")
out_h5seu <- paste0(base_path, name_sample, ".h5seurat")

# Ensure input exists
if (!file.exists(in_h5ad)) {
  stop(paste0("Cannot find h5ad file ", in_h5ad))
}

# Determine where outputs go
if (nzchar(output_root)) {
  if (!grepl("/$", output_root)) output_root <- paste0(output_root, "/")
  tissues_dir <- paste0(output_root, "tissues")
} else {
  tissues_dir <- paste0(base_path, "tissues")
}
if (!dir.exists(tissues_dir)) {
  dir.create(tissues_dir, recursive = TRUE, showWarnings = FALSE)
}

# Convert h5ad -> h5seurat and load
# IMPORTANT for batch mode: if a valid h5seurat already exists next to the h5ad
# AND it is newer than the h5ad, skip the (expensive) conversion.
# This caches the conversion across tasks within the same batch job.
need_convert <- TRUE
if (file.exists(out_h5seu)) {
  mtime_h5ad <- file.info(in_h5ad)$mtime
  mtime_seu  <- file.info(out_h5seu)$mtime
  if (!is.na(mtime_seu) && !is.na(mtime_h5ad) && mtime_seu >= mtime_h5ad) {
    need_convert <- FALSE
    cat("Reusing existing h5seurat cache:", out_h5seu, "\n")
  }
}
if (need_convert) {
  Convert(in_h5ad, dest = "h5seurat", overwrite = TRUE)
}

liver <- LoadH5Seurat(out_h5seu)

# Basic sanity checks (fail early with clear message)
if (!("Sample.Characteristic.individual" %in% colnames(liver[[]]))) {
  stop("Metadata column 'Sample.Characteristic.individual' not found in Seurat object.")
}
if (!("set" %in% colnames(liver[[]]))) {
  stop("Metadata column 'set' not found in Seurat object.")
}

# Selecting donor in dataset
Idents(liver) <- "Sample.Characteristic.individual"
if (!("donor1" %in% levels(Idents(liver)))) {
  stop("Identity 'donor1' not found in Sample.Characteristic.individual.")
}
donor1 <- subset(x = liver, idents = "donor1")

# Define immune/non-immune based on 'set'
# In your pipeline, immune cells are encoded as set == "1"
liver_to_remove <- c("1")

# Create a 'cell_type' column based on 'set' (as your original logic)
donor1[["cell_type"]] <- donor1[["set"]]

# Removing immune cells for the "no_immune" set
Idents(donor1) <- "cell_type"
donor1_no_immune <- subset(x = donor1, idents = liver_to_remove, invert = TRUE)

# Creating subset for immune cells only
donor1_immune <- subset(x = donor1, idents = liver_to_remove)

# Renaming immune cells for identification
donor1_immune[["cell_type"]] <- "immune cell"

# Add unique cell IDs required by SimBu
donor1_no_immune[["ID"]] <- rownames(donor1_no_immune[[]])
donor1_immune[["ID"]]    <- rownames(donor1_immune[[]])

# Combine datasets
combined <- merge(donor1_no_immune, y = donor1_immune)

# Build SimBu dataset
combined_simbu <- SimBu::dataset_seurat(
  seurat_obj     = combined,
  count_assay    = "RNA",
  #counts_layer   = "counts"
  cell_id_col    = "ID",
  cell_type_col  = "cell_type",
  name           = "combined",
  additional_cols = NULL
)

# Simulate bulk data
simulation <- SimBu::simulate_bulk(
  data              = combined_simbu,
  scenario          = "weighted",
  weighted_cell_type= "immune cell",
  weighted_amount   = immune_cell_fraction,
  scaling_factor    = "NONE",
  nsamples          = n_samples,
  ncells            = 10000,
  norm_counts       = TRUE,
  whitelist         = NULL,
  blacklist         = NULL,
  run_parallel      = FALSE
)

# Output paths
pdf_path <- paste0(tissues_dir, "/simbu_icf_", immune_cell_fraction, ".pdf")
txt_path <- paste0(tissues_dir, "/simbu_icf_", immune_cell_fraction, ".txt")

# Plot to PDF
pdf(pdf_path)
SimBu::plot_simulation(simulation)
dev.off()

# Save simulation results
SimBu::save_simulation(simulation, txt_path, assay = "bulk_counts")

# Emit machine-readable hints for the backend to parse
cat("PDF:", pdf_path, "\n")
cat("TXT:", txt_path, "\n")
cat("OK\n")
