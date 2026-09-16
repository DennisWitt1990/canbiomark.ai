"""Searching for single-cell datasets online.

Two sources, chosen after testing both:

**CELLxGENE Discover** is the browsing source. Its curation API lists every
collection with per-dataset ontology labels for tissue, organism, assay and
disease, which map straight onto the filters in the user interface, and each
dataset has a ``dataset_version_id`` that resolves to a downloadable ``.h5ad``.

**EBI BioStudies** is the targeted source. Its free-text search returns mostly
literature records -- a query for "single cell liver" yields over 900 000 hits,
almost all of them papers rather than datasets -- so it is offered only for
looking up a known accession such as ``E-MTAB-10553``.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..domain.dataset_import import (
    EBI_ACCESSION_PATTERN,
    DatasetSource,
    RemoteDataset,
)
from ..domain.errors import DomainError, ValidationError
from .tls_context import TlsContextProvider

_logger = logging.getLogger(__name__)

CELLXGENE_COLLECTIONS_URL = "https://api.cellxgene.cziscience.com/curation/v1/collections"
CELLXGENE_COLLECTION_URL = (
    "https://api.cellxgene.cziscience.com/curation/v1/collections/{collection_id}"
)
CELLXGENE_ASSET_URL = "https://datasets.cellxgene.cziscience.com/{version_id}.h5ad"
CELLXGENE_LANDING_URL = "https://cellxgene.cziscience.com/collections/{collection_id}"

BIOSTUDIES_STUDY_URL = "https://www.ebi.ac.uk/biostudies/api/v1/studies/{accession}"
BIOSTUDIES_LANDING_URL = "https://www.ebi.ac.uk/biostudies/studies/{accession}"

USER_AGENT = "CanBiomark.ai dataset importer/2.1"
REQUEST_TIMEOUT_SECONDS = 60
COLLECTION_CACHE_SECONDS = 900


class RemoteSourceError(DomainError):
    """A remote catalogue could not be reached or returned something unusable."""

    http_status_code = 502


class DatasetSearchService:
    """Queries the remote catalogues and normalises their answers."""

    def __init__(
        self,
        request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
        tls_context_provider: Optional[TlsContextProvider] = None,
    ) -> None:
        self._request_timeout_seconds = request_timeout_seconds
        self._tls_context_provider = tls_context_provider or TlsContextProvider()
        self._cached_collections: Optional[List[dict]] = None
        self._cached_at: float = 0.0

    # -- public API --------------------------------------------------------

    def search(
        self,
        *,
        source: DatasetSource,
        query: str,
        organism: Optional[str] = "Homo sapiens",
        limit: int = 40,
    ) -> List[RemoteDataset]:
        if source is DatasetSource.CELLXGENE:
            return self._search_cellxgene(query, organism, limit)
        return self._lookup_ebi_accession(query)

    def get_download_url(self, dataset: RemoteDataset) -> str:
        """The URL the importer streams the ``.h5ad`` from."""
        if dataset.source is DatasetSource.CELLXGENE:
            if not dataset.download_reference:
                raise ValidationError(
                    "This CELLxGENE dataset has no downloadable version id."
                )
            return CELLXGENE_ASSET_URL.format(version_id=dataset.download_reference)
        if not dataset.download_reference:
            raise ValidationError(
                "This dataset has no direct .h5ad download. Import it by "
                "accession once the file is published, or upload it manually."
            )
        return dataset.download_reference

    # -- CELLxGENE ---------------------------------------------------------

    def _search_cellxgene(
        self, query: str, organism: Optional[str], limit: int
    ) -> List[RemoteDataset]:
        collections = self._load_cellxgene_collections()
        search_terms = [term for term in (query or "").lower().split() if term]

        matches: List[RemoteDataset] = []
        for collection in collections:
            collection_name = str(collection.get("name") or "")
            collection_id = str(collection.get("collection_id") or "")

            for dataset in collection.get("datasets") or []:
                remote_dataset = self._to_remote_dataset(
                    collection_id, collection_name, collection, dataset
                )
                if not remote_dataset.matches_organism_filter(organism):
                    continue
                if search_terms and not self._matches_terms(
                    remote_dataset, collection_name, search_terms
                ):
                    continue
                matches.append(remote_dataset)
                if len(matches) >= limit:
                    return matches
        return matches

    def fetch_cellxgene_dataset(
        self, collection_id: str, dataset_id: str
    ) -> RemoteDataset:
        """Re-read one dataset, so an import never trusts client-supplied metadata."""
        payload = self._request_json(
            CELLXGENE_COLLECTION_URL.format(
                collection_id=urllib.parse.quote(collection_id, safe="")
            )
        )
        for dataset in payload.get("datasets") or []:
            if str(dataset.get("dataset_id")) == dataset_id:
                return self._to_remote_dataset(
                    collection_id, str(payload.get("name") or ""), payload, dataset
                )
        raise ValidationError(
            f"Dataset {dataset_id} is not part of collection {collection_id}."
        )

    def _load_cellxgene_collections(self) -> List[dict]:
        import time

        if (
            self._cached_collections is not None
            and time.time() - self._cached_at < COLLECTION_CACHE_SECONDS
        ):
            return self._cached_collections

        payload = self._request_json(CELLXGENE_COLLECTIONS_URL)
        if not isinstance(payload, list):
            raise RemoteSourceError("CELLxGENE returned an unexpected response.")

        self._cached_collections = payload
        self._cached_at = time.time()
        _logger.info("Loaded %s CELLxGENE collections.", len(payload))
        return payload

    def _to_remote_dataset(
        self,
        collection_id: str,
        collection_name: str,
        collection: dict,
        dataset: dict,
    ) -> RemoteDataset:
        return RemoteDataset(
            source=DatasetSource.CELLXGENE,
            dataset_id=str(dataset.get("dataset_id") or ""),
            title=str(dataset.get("title") or collection_name or "Untitled dataset"),
            collection_name=collection_name,
            organisms=self._ontology_labels(dataset.get("organism")),
            tissues=self._ontology_labels(dataset.get("tissue")),
            diseases=self._ontology_labels(dataset.get("disease")),
            assays=self._ontology_labels(dataset.get("assay")),
            cell_count=self._optional_int(dataset.get("cell_count")),
            publication_doi=str(collection.get("doi") or ""),
            landing_page_url=CELLXGENE_LANDING_URL.format(collection_id=collection_id),
            download_reference=str(dataset.get("dataset_version_id") or ""),
        )

    @staticmethod
    def _matches_terms(
        dataset: RemoteDataset, collection_name: str, search_terms: List[str]
    ) -> bool:
        """Every term must appear somewhere in the dataset's descriptive text."""
        haystack = " ".join(
            [
                dataset.title,
                collection_name,
                " ".join(dataset.tissues),
                " ".join(dataset.diseases),
                " ".join(dataset.assays),
                " ".join(dataset.organisms),
            ]
        ).lower()
        return all(term in haystack for term in search_terms)

    # -- EBI ---------------------------------------------------------------

    def _lookup_ebi_accession(self, query: str) -> List[RemoteDataset]:
        accession = (query or "").strip().upper()
        if not EBI_ACCESSION_PATTERN.match(accession):
            raise ValidationError(
                "Enter a BioStudies accession such as 'E-MTAB-10553'. The free-text "
                "search of BioStudies returns mostly publications rather than "
                "datasets, so it is not offered here -- use CELLxGENE to browse."
            )

        try:
            payload = self._request_json(
                BIOSTUDIES_STUDY_URL.format(accession=accession)
            )
        except RemoteSourceError:
            return []

        downloadable_files = self._collect_h5ad_files(payload)
        title = self._read_biostudies_title(payload) or accession

        return [
            RemoteDataset(
                source=DatasetSource.EBI_BIOSTUDIES,
                dataset_id=accession,
                title=title,
                collection_name=str(payload.get("collection") or "BioStudies"),
                landing_page_url=BIOSTUDIES_LANDING_URL.format(accession=accession),
                file_size_bytes=downloadable_files[0]["size"] if downloadable_files else None,
                download_reference=downloadable_files[0]["url"] if downloadable_files else "",
            )
        ]

    @staticmethod
    def _read_biostudies_title(payload: dict) -> str:
        for attribute in payload.get("attributes") or []:
            if str(attribute.get("name", "")).lower() == "title":
                return str(attribute.get("value") or "")
        return ""

    def _collect_h5ad_files(self, payload: dict) -> List[Dict[str, Any]]:
        """Walk the nested section tree and pick out ``.h5ad`` files."""
        found: List[Dict[str, Any]] = []
        accession = str(payload.get("accno") or "")

        def visit(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    visit(item)
                return
            if not isinstance(node, dict):
                return

            path = node.get("path")
            if isinstance(path, str) and path.lower().endswith(".h5ad"):
                found.append(
                    {
                        "url": (
                            "https://www.ebi.ac.uk/biostudies/files/"
                            f"{accession}/{urllib.parse.quote(path)}"
                        ),
                        "size": DatasetSearchService._read_file_size(node),
                    }
                )
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)

        visit(payload.get("section"))
        visit(payload.get("files"))
        return found

    @staticmethod
    def _read_file_size(node: dict) -> Optional[int]:
        raw_size = node.get("size")
        if isinstance(raw_size, int):
            return raw_size
        for attribute in node.get("attributes") or []:
            if str(attribute.get("name", "")).lower() == "size":
                return DatasetSearchService._optional_int(attribute.get("value"))
        return None

    # -- shared helpers ----------------------------------------------------

    def _request_json(self, url: str) -> Any:
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._request_timeout_seconds,
                context=self._tls_context_provider.build(),
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise RemoteSourceError("The requested record does not exist.") from error
            raise RemoteSourceError(
                f"The remote catalogue answered with HTTP {error.code}."
            ) from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RemoteSourceError(
                f"The remote catalogue could not be reached: {error}"
            ) from error

    @staticmethod
    def _ontology_labels(raw_value: Any) -> List[str]:
        """CELLxGENE returns ``[{"label": ..., "ontology_term_id": ...}, ...]``."""
        if not isinstance(raw_value, list):
            return []
        labels: List[str] = []
        for entry in raw_value:
            if isinstance(entry, dict) and entry.get("label"):
                labels.append(str(entry["label"]))
            elif isinstance(entry, str):
                labels.append(entry)
        return labels

    @staticmethod
    def _optional_int(raw_value: Any) -> Optional[int]:
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None
