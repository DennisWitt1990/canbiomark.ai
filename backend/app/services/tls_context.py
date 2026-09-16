"""A TLS context that also works where the system trust store is not wired up.

On macOS a Python installed from python.org ships without a usable CA bundle,
so ``ssl.create_default_context()`` fails every HTTPS request with
``CERTIFICATE_VERIFY_FAILED`` even though ``curl`` works. The predecessor
downloader hit the same wall and solved it with ``certifi``; the same order is
used here.

Verification is never disabled silently. ``allow_insecure`` exists for an
operator who knowingly accepts the risk on a broken host, and it logs a warning
every time it is used.
"""
from __future__ import annotations

import logging
import ssl
from functools import lru_cache
from typing import Optional

_logger = logging.getLogger(__name__)


class TlsContextProvider:
    """Builds the SSL context used for every outbound request."""

    def __init__(
        self,
        certificate_bundle_path: Optional[str] = None,
        allow_insecure: bool = False,
    ) -> None:
        self._certificate_bundle_path = certificate_bundle_path
        self._allow_insecure = allow_insecure

    def build(self) -> ssl.SSLContext:
        if self._allow_insecure:
            _logger.warning(
                "TLS verification is DISABLED for outbound dataset downloads. "
                "Downloaded files are not authenticated."
            )
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context

        if self._certificate_bundle_path:
            return ssl.create_default_context(cafile=self._certificate_bundle_path)

        bundle_path = _find_certifi_bundle()
        if bundle_path:
            return ssl.create_default_context(cafile=bundle_path)

        return ssl.create_default_context()


@lru_cache(maxsize=1)
def _find_certifi_bundle() -> Optional[str]:
    """Path to the certifi CA bundle, when certifi is installed."""
    try:
        import certifi

        return certifi.where()
    except Exception:  # noqa: BLE001 - certifi is optional
        _logger.debug("certifi is not available; using the system trust store.")
        return None
