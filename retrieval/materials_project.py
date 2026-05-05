"""Materials Project retriever using mp-api and normalized CatalystRecord mapping."""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import MP_API_KEY
from retrieval.base import BaseRetriever, CatalystRecord, RetrieverConnectionError, RetrieverParseError


class MaterialsProjectRetriever(BaseRetriever):
    """Retrieve catalyst candidates from Materials Project summaries."""

    source_name = "Materials Project"
    _element_pattern = re.compile(r"\b([A-Z][a-z]?)\b")

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize retriever with API key.

        Args:
            api_key: Optional explicit MP API key override.

        Returns:
            None.

        Raises:
            None.
        """
        self.api_key = api_key or MP_API_KEY
        self._mp_import_error: str | None = None

    def _parse_elements(self, reaction: str) -> list[str]:
        """Extract probable chemical element symbols from query.

        Args:
            reaction: Free-text reaction string.

        Returns:
            Sorted unique list of symbols.

        Raises:
            None.
        """
        matches = self._element_pattern.findall(reaction or "")
        return sorted(set(matches))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _query_materials(self, elements: list[str]) -> list[Any]:
        """Call Materials Project summary endpoint for element-constrained search.

        Args:
            elements: Chemical element symbols.

        Returns:
            List of mp-api summary documents.

        Raises:
            RetrieverConnectionError: If API key is missing or API call fails.
        """
        if not self.api_key:
            raise RetrieverConnectionError("Missing Materials Project API key.")

        try:
            from mp_api.client import MPRester
        except Exception as exc:  # noqa: BLE001
            self._mp_import_error = str(exc)
            raise RetrieverConnectionError(f"Failed to import mp-api client: {exc}") from exc

        try:
            with MPRester(self.api_key) as mpr:
                docs = mpr.materials.summary.search(elements=elements, fields=["material_id", "formula_pretty", "formation_energy_per_atom", "energy_above_hull"])
                return list(docs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Materials Project query failed for elements={}", elements)
            raise RetrieverConnectionError(str(exc)) from exc

    def search(self, reaction: str) -> list[CatalystRecord]:
        """Fetch and normalize stable material candidates.

        Args:
            reaction: Reaction text used for element extraction.

        Returns:
            List of CatalystRecord items.

        Raises:
            RetrieverParseError: If response parsing fails unexpectedly.
        """
        if not self.api_key:
            logger.warning("Materials Project API key missing; returning empty result.")
            return []

        elements = self._parse_elements(reaction)
        if not elements:
            logger.warning("No element symbols parsed from reaction='{}'", reaction)
            return []

        try:
            docs = self._query_materials(elements=elements)
            records: list[CatalystRecord] = []
            for doc in docs:
                energy_above_hull = getattr(doc, "energy_above_hull", None)
                if energy_above_hull is None or energy_above_hull >= 0.1:
                    continue

                formation_energy = getattr(doc, "formation_energy_per_atom", None)
                material_id = str(getattr(doc, "material_id", ""))
                formula_pretty = str(getattr(doc, "formula_pretty", ""))

                record = CatalystRecord(
                    source=self.source_name,
                    source_id=material_id,
                    name=f"MP {material_id}",
                    formula=formula_pretty,
                    reaction=reaction,
                    activity_metric="formation_energy_per_atom",
                    activity_value=float(formation_energy) if formation_energy is not None else None,
                    activity_unit="eV/atom",
                    conditions={},
                    stability=float(energy_above_hull),
                    raw={
                        "material_id": material_id,
                        "formula_pretty": formula_pretty,
                        "formation_energy_per_atom": formation_energy,
                        "energy_above_hull": energy_above_hull,
                    },
                )
                records.append(record)

            logger.info("Materials Project returned {} stable candidates.", len(records))
            return records
        except RetrieverConnectionError:
            logger.warning("Materials Project connection issue; returning empty results.")
            return []
        except Exception as exc:  # noqa: BLE001
            raise RetrieverParseError(f"Failed to parse Materials Project payload: {exc}") from exc

    def health_check(self) -> bool:
        """Check retriever readiness and API reachability.

        Args:
            None.

        Returns:
            True if API key exists and minimal query succeeds.

        Raises:
            None.
        """
        if not self.api_key:
            return False
        if self._mp_import_error:
            logger.warning("Materials Project disabled due to import error: {}", self._mp_import_error)
            return False
        try:
            _ = self._query_materials(elements=["H"])
            return True
        except Exception:  # noqa: BLE001
            return False
