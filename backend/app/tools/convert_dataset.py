#!/usr/bin/env python3
"""Convert a downloaded dataset into an anndata 0.7.6 readable file.

This runs in its **own interpreter**, and that is the whole point.

The application is pinned to ``anndata==0.7.6`` because the SeuratDisk commit
SimBu depends on can only read what that version writes. But 0.7.6 also cannot
*read* what modern anndata writes, and every dataset downloaded from CELLxGENE
or EBI is written by a modern version. The predecessor downloader documents the
same split: "run in a MODERN anndata env; the result is then read by your SimBu
env".

So the container ships two virtual environments, and the import service calls
this script with the modern interpreter. The conversion itself reuses
``AnnDataCompatibilityConverter`` -- the logic is not duplicated, only executed
elsewhere.

Usage::

    python -m app.tools.convert_dataset \
        --input downloaded.h5ad --output converted.h5ad \
        --cell-type-column "Supertype" --source-id abc123 [--promote-raw]

On success it prints one JSON object to stdout describing the result.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running as a script inside the modern environment, where the package
# may not be installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.anndata_compatibility import (  # noqa: E402
    AnnDataCompatibilityConverter,
)

CELL_TYPE_COLUMN = "cell_type"


def promote_raw_counts_and_symbols(dataset):
    """Use ``.raw.X`` and HGNC symbols, as the CELLxGENE schema requires.

    ``.X`` holds normalised values while SimBu needs raw counts, and
    ``var.index`` is an Ensembl id while the downstream gene lists use symbols.
    """
    import anndata

    if dataset.raw is not None:
        promoted = anndata.AnnData(
            X=dataset.raw.X, obs=dataset.obs.copy(), var=dataset.raw.var.copy()
        )
        promoted.obs_names = dataset.obs_names
        dataset = promoted
    else:
        logging.warning(
            "The dataset has no .raw; .X is assumed to hold raw counts, "
            "which is unusual for CELLxGENE."
        )

    if "feature_name" in dataset.var.columns:
        symbols = dataset.var["feature_name"].astype(str)
        duplicated = symbols.duplicated(keep="first")
        if duplicated.any():
            # First occurrence wins; counts are never summed silently.
            dataset = dataset[:, ~duplicated].copy()
            symbols = symbols[~duplicated]
        dataset.var_names = symbols.to_numpy()
        dataset.var_names.name = "gene_symbol"

    return dataset


def convert(
    *,
    input_path: Path,
    output_path: Path,
    cell_type_column: str,
    source_id: str,
    should_promote_raw: bool,
) -> dict:
    import anndata

    dataset = anndata.read_h5ad(input_path)

    if cell_type_column not in dataset.obs.columns:
        raise SystemExit(
            f"Column {cell_type_column!r} is not present in the dataset."
        )

    if should_promote_raw:
        dataset = promote_raw_counts_and_symbols(dataset)
        if cell_type_column not in dataset.obs.columns:
            raise SystemExit(
                f"Column {cell_type_column!r} is gone after switching to the raw counts."
            )

    dataset.obs[CELL_TYPE_COLUMN] = dataset.obs[cell_type_column].astype(str)
    dataset.obs["source_dataset"] = source_id
    dataset.obs["source_cell_type_column"] = cell_type_column

    distinct_cell_types = int(dataset.obs[CELL_TYPE_COLUMN].nunique())
    cell_count, gene_count = int(dataset.n_obs), int(dataset.n_vars)

    report = AnnDataCompatibilityConverter().write_readable(dataset, output_path)

    return {
        "ok": True,
        "anndata_version": anndata.__version__,
        "cell_count": cell_count,
        "gene_count": gene_count,
        "distinct_cell_types": distinct_cell_types,
        "stripped_groups": len(report.stripped_groups),
        "pinned_dataframe_versions": len(report.pinned_dataframe_versions),
        "output_path": str(output_path),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cell-type-column", required=True)
    parser.add_argument("--source-id", default="")
    parser.add_argument(
        "--promote-raw",
        action="store_true",
        help="Use .raw.X and var.feature_name (CELLxGENE datasets).",
    )
    arguments = parser.parse_args()

    result = convert(
        input_path=arguments.input,
        output_path=arguments.output,
        cell_type_column=arguments.cell_type_column,
        source_id=arguments.source_id,
        should_promote_raw=arguments.promote_raw,
    )
    # stdout carries the machine-readable result; logs go to stderr.
    print(json.dumps(result))


if __name__ == "__main__":
    main()
