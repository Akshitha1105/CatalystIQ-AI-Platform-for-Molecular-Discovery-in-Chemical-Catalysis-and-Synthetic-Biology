"""BRENDA SOAP retriever using zeep with credential hashing and cache integration."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from zeep import Client
from zeep.transports import Transport

from config import BRENDA_EMAIL, BRENDA_PASSWORD, CACHE_DB_PATH
from processing.cache import QueryCache
from retrieval.base import BaseRetriever, CatalystRecord, RetrieverConnectionError, RetrieverParseError

BRENDA_WSDL = "https://www.brenda-enzymes.org/soap/brenda_zeep.wsdl"


class BrendaRetriever(BaseRetriever):
    """Retrieve enzyme kinetics candidates from BRENDA SOAP service."""

    source_name = "BRENDA"

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        cache: QueryCache | None = None,
    ) -> None:
        """Initialize BRENDA retriever dependencies.

        Args:
            email: Optional BRENDA account email.
            password: Optional BRENDA account password.
            cache: Optional query cache instance.

        Returns:
            None.

        Raises:
            None.
        """
        self.email = email or BRENDA_EMAIL
        self.password = password or BRENDA_PASSWORD
        self.cache = cache or QueryCache(CACHE_DB_PATH)

    def _parse_substrate(self, reaction: str) -> str:
        """Extract substrate token from reaction string.

        Args:
            reaction: Free-text reaction expression.

        Returns:
            Best-effort substrate name.

        Raises:
            None.
        """
        if "→" in reaction:
            return reaction.split("→", maxsplit=1)[0].split("+")[0].strip()
        if "->" in reaction:
            return reaction.split("->", maxsplit=1)[0].split("+")[0].strip()
        tokenized = re.split(r"\s+", reaction.strip())
        return tokenized[0] if tokenized else reaction.strip()

    def _hash_password(self) -> str:
        """Hash the BRENDA password with SHA-256.

        Args:
            None.

        Returns:
            SHA-256 digest string.

        Raises:
            None.
        """
        return hashlib.sha256(self.password.encode("utf-8")).hexdigest()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _soap_get_km(self, substrate: str) -> list[dict[str, Any]]:
        """Call BRENDA getKmValue via SOAP and normalize response shape.

        Args:
            substrate: Substrate keyword.

        Returns:
            List of raw response dictionaries.

        Raises:
            RetrieverConnectionError: If SOAP call fails.
        """
        try:
            client = Client(wsdl=BRENDA_WSDL, transport=Transport(timeout=20))
            parameters = f"email*{self.email}#password*{self._hash_password()}#substrate*{substrate}"
            response = client.service.getKmValue(parameters)
        except Exception as exc:  # noqa: BLE001
            logger.exception("BRENDA SOAP call failed for substrate={}", substrate)
            raise RetrieverConnectionError(str(exc)) from exc

        if response is None:
            return []
        if isinstance(response, list):
            return [entry if isinstance(entry, dict) else {"value": entry} for entry in response]
        if isinstance(response, dict):
            return [response]
        return [{"value": response}]

    def search(self, reaction: str) -> list[CatalystRecord]:
        """Retrieve Km values for parsed substrate and map to CatalystRecord.

        Args:
            reaction: Reaction text to parse substrate.

        Returns:
            List of CatalystRecord items.

        Raises:
            RetrieverParseError: If response mapping fails unexpectedly.
        """
        if not self.email or not self.password:
            logger.warning("BRENDA credentials missing; returning empty result.")
            return []

        substrate = self._parse_substrate(reaction)
        query = {"substrate": substrate}
        cached = self.cache.get(self.source_name, query)
        raw_entries: list[dict[str, Any]]

        if cached is not None:
            raw_entries = cached.get("entries", [])
        else:
            try:
                raw_entries = self._soap_get_km(substrate=substrate)
            except RetrieverConnectionError:
                logger.warning("BRENDA unavailable for substrate='{}'; returning empty result.", substrate)
                return []
            self.cache.set(self.source_name, query, {"entries": raw_entries})

        try:
            records: list[CatalystRecord] = []
            for idx, entry in enumerate(raw_entries):
                enzyme_name = str(entry.get("enzyme_name") or entry.get("recommended_name") or "Unknown enzyme")
                organism = str(entry.get("organism") or "Unknown organism")
                km_raw = entry.get("km_value") or entry.get("value")
                unit = str(entry.get("km_unit") or entry.get("unit") or "mM")

                km_value: float | None
                try:
                    km_value = float(km_raw) if km_raw is not None else None
                except (TypeError, ValueError):
                    km_value = None

                record = CatalystRecord(
                    source=self.source_name,
                    source_id=str(entry.get("id") or f"brenda-km-{idx}"),
                    name=enzyme_name,
                    formula="",
                    reaction=reaction,
                    activity_metric="Km",
                    activity_value=km_value,
                    activity_unit=unit,
                    conditions={"organism": organism, "substrate": substrate},
                    stability=None,
                    raw=entry,
                )
                records.append(record)

            logger.info("BRENDA returned {} candidates for substrate='{}'.", len(records), substrate)
            return records
        except Exception as exc:  # noqa: BLE001
            raise RetrieverParseError(f"Failed to parse BRENDA response: {exc}") from exc

    def health_check(self) -> bool:
        """Check whether BRENDA retriever can execute a minimal request.

        Args:
            None.

        Returns:
            True when credentials exist and SOAP endpoint responds.

        Raises:
            None.
        """
        if not self.email or not self.password:
            return False
        try:
            _ = self._soap_get_km(substrate="glucose")
            return True
        except Exception:  # noqa: BLE001
            return False
