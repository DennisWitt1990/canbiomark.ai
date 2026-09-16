"""Streams a remote ``.h5ad`` to disk with progress and a size guard."""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ..domain.errors import DomainError, ValidationError
from .tls_context import TlsContextProvider

_logger = logging.getLogger(__name__)

CHUNK_SIZE_BYTES = 1024 * 1024
USER_AGENT = "CanBiomark.ai dataset importer/2.1"

ProgressCallback = Callable[[int, Optional[int]], None]


class DownloadError(DomainError):
    """A dataset could not be downloaded."""

    http_status_code = 502


class DatasetDownloader:
    """Downloads a dataset file, reporting progress as it goes."""

    def __init__(
        self,
        tls_context_provider: Optional[TlsContextProvider] = None,
        maximum_file_size_bytes: Optional[int] = None,
        connect_timeout_seconds: int = 120,
    ) -> None:
        self._tls_context_provider = tls_context_provider or TlsContextProvider()
        self._maximum_file_size_bytes = maximum_file_size_bytes
        self._connect_timeout_seconds = connect_timeout_seconds

    def probe_size(self, url: str) -> Optional[int]:
        """Ask for the size without downloading, so a quota can be checked first."""
        request = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._connect_timeout_seconds,
                context=self._tls_context_provider.build(),
            ) as response:
                raw_length = response.headers.get("Content-Length")
                return int(raw_length) if raw_length else None
        except (urllib.error.URLError, ValueError, TimeoutError) as error:
            _logger.debug("Could not probe the size of %s: %s", url, error)
            return None

    def download(
        self,
        url: str,
        target_path: Path,
        report_progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Path:
        """Stream ``url`` into ``target_path``.

        The file is written to a ``.part`` sibling and renamed only after a
        complete transfer, so an interrupted download never leaves something
        that looks like a usable dataset.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = target_path.with_suffix(target_path.suffix + ".part")

        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        downloaded_bytes = 0

        try:
            with urllib.request.urlopen(
                request,
                timeout=self._connect_timeout_seconds,
                context=self._tls_context_provider.build(),
            ) as response:
                raw_length = response.headers.get("Content-Length")
                expected_bytes = int(raw_length) if raw_length else None
                self._assert_within_limit(expected_bytes)

                with partial_path.open("wb") as target_file:
                    while True:
                        if should_cancel is not None and should_cancel():
                            raise DownloadError("The download was cancelled.")

                        chunk = response.read(CHUNK_SIZE_BYTES)
                        if not chunk:
                            break

                        target_file.write(chunk)
                        downloaded_bytes += len(chunk)
                        self._assert_within_limit(downloaded_bytes)

                        if report_progress is not None:
                            report_progress(downloaded_bytes, expected_bytes)

                if expected_bytes is not None and downloaded_bytes != expected_bytes:
                    raise DownloadError(
                        f"The download is incomplete: {downloaded_bytes} of "
                        f"{expected_bytes} bytes arrived."
                    )

            partial_path.replace(target_path)
            _logger.info("Downloaded %s bytes to %s", downloaded_bytes, target_path)
            return target_path

        except urllib.error.HTTPError as error:
            self._discard(partial_path)
            raise DownloadError(
                f"The source answered with HTTP {error.code} for {url}."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            self._discard(partial_path)
            raise DownloadError(f"The download failed: {error}") from error
        except Exception:
            self._discard(partial_path)
            raise

    def _assert_within_limit(self, size_bytes: Optional[int]) -> None:
        if size_bytes is None or self._maximum_file_size_bytes is None:
            return
        if size_bytes > self._maximum_file_size_bytes:
            raise ValidationError(
                f"The dataset is larger than the configured limit of "
                f"{self._maximum_file_size_bytes // (1024 * 1024)} MB."
            )

    @staticmethod
    def _discard(partial_path: Path) -> None:
        try:
            partial_path.unlink(missing_ok=True)
        except OSError:
            _logger.debug("Could not remove %s", partial_path)
