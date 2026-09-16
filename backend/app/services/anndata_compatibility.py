"""Makes a modern ``.h5ad`` readable by anndata 0.7.6.

Why this is needed at all
-------------------------
The SimBu step runs through SeuratDisk, and the SeuratDisk commit this project
pins can only read what anndata **0.7.6** writes. That reader accepts group
``encoding-type`` values of only ``raw``, ``dataframe``, ``csr_matrix`` and
``csc_matrix``. Modern anndata (>= 0.8) writes container groups as ``dict``,
string columns as ``categorical`` groups, and pandas nullable columns as
``nullable-integer`` / ``nullable-boolean``; every one of those makes 0.7.6
raise. Datasets downloaded from CELLxGENE or EBI are written by modern anndata,
so they must be converted before they can enter the catalogue.

The three steps -- ``sanitize`` in memory, ``harden`` on the written file, then
``verify`` by emulating the old reader -- are ported from the predecessor
downloader (``weiterer Code/NewDownloaderANDConverter/fetch_biostudies_h5ad.py``),
whose logic was validated against the anndata 0.7.6 source. Verification is
pure ``h5py`` and therefore runs in any environment, including this one, where
anndata 0.7.6 itself is installed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Tuple

from ..domain.errors import DomainError

_logger = logging.getLogger(__name__)

# The only group encodings the 0.7.6 reader understands.
READABLE_GROUP_ENCODINGS = frozenset({"raw", "dataframe", "csr_matrix", "csc_matrix"})
# Container encodings that modern anndata adds and that can simply be dropped.
STRIPPABLE_GROUP_ENCODINGS = frozenset({"dict", "anndata"})
HIGHEST_KNOWN_ENCODING_VERSION = {
    "raw": "0.1.0",
    "csr_matrix": "0.1.0",
    "csc_matrix": "0.1.0",
    "dataframe": "0.1.0",
}


class AnnDataCompatibilityError(DomainError):
    """A dataset cannot be made readable by anndata 0.7.6."""

    http_status_code = 422


@dataclass
class CompatibilityReport:
    """What the conversion changed and whether the result verifies."""

    stripped_groups: List[Tuple[str, str]] = field(default_factory=list)
    pinned_dataframe_versions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_readable(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"{len(self.stripped_groups)} group(s) stripped, "
            f"{len(self.pinned_dataframe_versions)} dataframe version(s) pinned, "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


class AnnDataCompatibilityConverter:
    """Converts and verifies datasets for the pinned anndata 0.7.6 reader."""

    # -- step 1: in-memory sanitation --------------------------------------

    def sanitize(self, dataset: Any) -> Any:
        """Replace categorical and nullable dtypes, normalise sparse matrices."""
        import anndata
        import pandas

        dataset.obs = self._plain_frame(dataset.obs)
        dataset.var = self._plain_frame(dataset.var)
        dataset.X = self._normalize_matrix(dataset.X)

        for layer_name in list(dataset.layers.keys()):
            dataset.layers[layer_name] = self._normalize_matrix(dataset.layers[layer_name])
        for pair_name in list(dataset.obsp.keys()):
            dataset.obsp[pair_name] = self._normalize_matrix(dataset.obsp[pair_name])
        for pair_name in list(dataset.varp.keys()):
            dataset.varp[pair_name] = self._normalize_matrix(dataset.varp[pair_name])

        dataset.uns = self._plain_unstructured(dict(dataset.uns))

        if dataset.raw is not None:
            dataset.raw = anndata.AnnData(
                X=self._normalize_matrix(dataset.raw.X),
                var=self._plain_frame(dataset.raw.var.copy()),
                obs=pandas.DataFrame(index=dataset.obs_names),
            )
        return dataset

    def write_readable(self, dataset: Any, target_path: Path) -> CompatibilityReport:
        """Sanitize, write, harden and verify in one call."""
        dataset = self.sanitize(dataset)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Without this flag anndata re-categorises every string column on write,
        # undoing the sanitation.
        dataset.write_h5ad(target_path, convert_strings_to_categoricals=False)

        report = self.harden(target_path)
        verification = self.verify(target_path)
        report.errors.extend(verification.errors)
        report.warnings.extend(verification.warnings)

        if not report.is_readable:
            raise AnnDataCompatibilityError(
                "The dataset could not be made readable by anndata 0.7.6:\n"
                + "\n".join(report.errors[:10])
            )
        return report

    # -- step 2: on-file hardening -----------------------------------------

    def harden(self, dataset_path: Path) -> CompatibilityReport:
        """Rewrite group attributes so the old reader accepts every group."""
        import h5py

        report = CompatibilityReport()
        unfixable: List[Tuple[str, str]] = []

        with h5py.File(dataset_path, "r+") as h5_file:

            def visit(name: str, node) -> None:
                if not isinstance(node, h5py.Group):
                    return
                encoding_type = self._read_attribute(node, "encoding-type")
                if encoding_type is None:
                    return

                if encoding_type in READABLE_GROUP_ENCODINGS:
                    if (
                        encoding_type == "dataframe"
                        and self._read_attribute(node, "encoding-version") != "0.1.0"
                    ):
                        node.attrs["encoding-version"] = "0.1.0"
                        report.pinned_dataframe_versions.append(name)
                    return

                if encoding_type in STRIPPABLE_GROUP_ENCODINGS:
                    del node.attrs["encoding-type"]
                    if "encoding-version" in node.attrs:
                        del node.attrs["encoding-version"]
                    report.stripped_groups.append((name, encoding_type))
                else:
                    unfixable.append((name, encoding_type))

            h5_file.visititems(visit)

            root_encoding = self._read_attribute(h5_file, "encoding-type")
            if root_encoding is not None and root_encoding not in READABLE_GROUP_ENCODINGS:
                del h5_file.attrs["encoding-type"]
                if "encoding-version" in h5_file.attrs:
                    del h5_file.attrs["encoding-version"]
                report.stripped_groups.append(("/", root_encoding))

        if unfixable:
            raise AnnDataCompatibilityError(
                "These groups cannot be made 0.7.6-readable, which means the "
                f"sanitation step missed something: {unfixable}"
            )
        return report

    # -- step 3: verification ----------------------------------------------

    def verify(self, dataset_path: Path) -> CompatibilityReport:
        """Emulate the anndata 0.7.6 reader; pure h5py, no anndata needed."""
        import h5py

        report = CompatibilityReport()

        def check_group(name: str, group) -> None:
            if "h5sparse_format" in group.attrs:
                return  # legacy sparse layout, readable as is
            encoding_type = self._read_attribute(group, "encoding-type")
            if encoding_type is None:
                return

            if encoding_type not in READABLE_GROUP_ENCODINGS:
                report.errors.append(
                    f"{name}: unreadable encoding-type {encoding_type!r}"
                )
                return

            encoding_version = self._read_attribute(group, "encoding-version")
            highest_known = HIGHEST_KNOWN_ENCODING_VERSION.get(encoding_type)
            if (
                highest_known
                and encoding_version is not None
                and str(encoding_version) > highest_known
            ):
                report.warnings.append(
                    f"{name}: {encoding_type} v{encoding_version} is newer than "
                    f"v{highest_known}"
                )

            if encoding_type == "dataframe":
                self._check_dataframe_group(name, group, report)
            elif encoding_type in {"csr_matrix", "csc_matrix"}:
                self._check_sparse_group(name, group, report)

        with h5py.File(dataset_path, "r") as h5_file:
            h5_file.visititems(
                lambda name, node: check_group(name, node)
                if isinstance(node, h5py.Group)
                else None
            )

        _logger.info(
            "anndata 0.7.6 verification of %s: %s", dataset_path.name, report.summary()
        )
        return report

    def _check_dataframe_group(self, name: str, group, report: CompatibilityReport) -> None:
        import h5py

        if "column-order" not in group.attrs or "_index" not in group.attrs:
            report.errors.append(f"{name}: dataframe without column-order or _index")
            return

        index_name = self._read_attribute(group, "_index")
        if index_name not in group:
            report.errors.append(f"{name}: index dataset {index_name!r} is missing")

        for raw_column in group.attrs["column-order"]:
            column_name = (
                raw_column.decode() if isinstance(raw_column, bytes) else str(raw_column)
            )
            if column_name not in group:
                report.errors.append(f"{name}/{column_name}: column is missing")
            elif isinstance(group[column_name], h5py.Group):
                report.errors.append(
                    f"{name}/{column_name}: column is a GROUP, which breaks 0.7.6"
                )

    @staticmethod
    def _check_sparse_group(name: str, group, report: CompatibilityReport) -> None:
        if "shape" not in group.attrs and "h5sparse_shape" not in group.attrs:
            report.errors.append(f"{name}: sparse matrix without a shape attribute")
        for required_dataset in ("data", "indices", "indptr"):
            if required_dataset not in group:
                report.errors.append(
                    f"{name}: sparse matrix without {required_dataset!r}"
                )

    # -- dtype conversion --------------------------------------------------

    @staticmethod
    def _plain_series(series):
        """Convert one column to a dtype both the writer and 0.7.6 accept."""
        import numpy
        import pandas

        dtype = series.dtype
        has_missing_values = bool(series.isna().any())

        if isinstance(dtype, pandas.CategoricalDtype):
            category_dtype = series.cat.categories.dtype
            if pandas.api.types.is_bool_dtype(category_dtype) and not has_missing_values:
                values = series.astype(bool).to_numpy()
            elif (
                pandas.api.types.is_integer_dtype(category_dtype)
                and not has_missing_values
            ):
                values = series.astype("int64").to_numpy()
            elif pandas.api.types.is_float_dtype(category_dtype):
                values = series.astype("float64").to_numpy()
            else:
                values = series.astype(str).to_numpy().astype(object)
            return pandas.Series(values, index=series.index, name=series.name)

        if pandas.api.types.is_extension_array_dtype(dtype):
            if pandas.api.types.is_integer_dtype(dtype):
                values = (
                    series.to_numpy(dtype="float64", na_value=numpy.nan)
                    if has_missing_values
                    else series.to_numpy(dtype="int64")
                )
            elif pandas.api.types.is_float_dtype(dtype):
                values = series.to_numpy(dtype="float64", na_value=numpy.nan)
            elif pandas.api.types.is_bool_dtype(dtype):
                values = (
                    series.astype(str).to_numpy().astype(object)
                    if has_missing_values
                    else series.to_numpy(dtype=bool)
                )
            else:
                values = series.astype(str).to_numpy().astype(object)
            return pandas.Series(values, index=series.index, name=series.name)

        if dtype == object:
            return pandas.Series(
                series.astype(str).to_numpy().astype(object),
                index=series.index,
                name=series.name,
            )
        return series

    @classmethod
    def _plain_frame(cls, frame):
        import pandas

        converted = pandas.DataFrame(index=frame.index.astype(str))
        for column_name in frame.columns:
            converted[column_name] = cls._plain_series(frame[column_name]).values
        converted.index.name = frame.index.name
        return converted

    @classmethod
    def _plain_unstructured(cls, value: Any) -> Any:
        """Recursively clean ``uns``, which may nest frames and categoricals."""
        import numpy
        import pandas

        if isinstance(value, dict):
            return {key: cls._plain_unstructured(item) for key, item in value.items()}
        if isinstance(value, pandas.DataFrame):
            return cls._plain_frame(value)
        if isinstance(value, pandas.Series):
            return cls._plain_series(value).values
        if isinstance(value, pandas.Categorical):
            return numpy.asarray(value.astype(object))
        return value

    @staticmethod
    def _normalize_matrix(matrix):
        """0.7.6 reads only CSR and CSC, with sorted indices."""
        from scipy import sparse

        if sparse.issparse(matrix):
            if not isinstance(matrix, (sparse.csr_matrix, sparse.csc_matrix)):
                matrix = matrix.tocsr()
            matrix.sort_indices()
        return matrix

    @staticmethod
    def _read_attribute(node, attribute_name: str) -> Any:
        raw_value = node.attrs.get(attribute_name)
        if isinstance(raw_value, bytes):
            return raw_value.decode("utf-8", errors="replace")
        return raw_value
