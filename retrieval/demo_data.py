"""Demo candidate dataset generator for offline testing and fallback retrieval."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd

DEMO_SOURCES = ("Materials Project", "BRENDA", "Open Catalyst")

DEMO_REACTION_LIBRARY = [
    "Fe + O2 -> Fe2O3",
    "Ni + O2 -> NiO",
    "CO2 + H2 -> methanol",
    "CO + H2 -> methane",
    "N2 + H2 -> NH3",
    "glucose + ATP -> glucose-6-phosphate + ADP",
    "lactose -> glucose + galactose",
]

DEMO_FORMULAS = [
    "Fe2O3",
    "NiO",
    "CuO",
    "Co3O4",
    "ZnO",
    "TiO2",
    "CeO2",
    "RuO2",
    "Pt",
    "Pd",
    "FeNi",
    "Mo2C",
    "WC",
    "V2O5",
    "MnO2",
]


def _deterministic_value(seed: str, lower: float, upper: float) -> float:
    """Create deterministic pseudo-random float between bounds.

    Args:
        seed: Hash input seed string.
        lower: Lower numeric bound.
        upper: Upper numeric bound.

    Returns:
        Deterministic float in the provided range.

    Raises:
        ValueError: If lower bound is greater than upper bound.
    """
    if lower > upper:
        raise ValueError("lower bound must be <= upper bound")
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    scale = int(digest[:8], 16) / 0xFFFFFFFF
    return lower + (upper - lower) * scale


def build_demo_candidates(limit: int = 120) -> pd.DataFrame:
    """Generate a broad in-memory demo catalog across sources and reactions.

    Args:
        limit: Maximum number of generated rows.

    Returns:
        DataFrame containing demo candidate rows.

    Raises:
        None.
    """
    rows: list[dict[str, Any]] = []
    for source in DEMO_SOURCES:
        for reaction in DEMO_REACTION_LIBRARY:
            for formula in DEMO_FORMULAS:
                seed = f"{source}|{reaction}|{formula}"
                if source == "Materials Project":
                    unit = "eV/atom"
                    metric = "formation_energy_per_atom"
                    value = _deterministic_value(seed, -2.5, 0.6)
                elif source == "Open Catalyst":
                    unit = "eV"
                    metric = "adsorption_energy"
                    value = _deterministic_value(seed, -1.8, 1.8)
                else:
                    unit = "mM"
                    metric = "Km"
                    value = _deterministic_value(seed, 0.02, 15.0)

                rows.append(
                    {
                        "source": source,
                        "source_id": f"demo-{abs(hash(seed)) % 1000000}",
                        "name": f"Demo {formula} ({source})",
                        "formula": formula if source != "BRENDA" else "",
                        "reaction": reaction,
                        "activity_metric": metric,
                        "activity_value": round(value, 5),
                        "activity_unit": unit,
                        "conditions": {
                            "temperature_k": int(_deterministic_value(seed + "temp", 260, 980)),
                            "ph": round(_deterministic_value(seed + "ph", 3.0, 11.0), 1),
                            "organism": "Demo organism" if source == "BRENDA" else "",
                        },
                        "stability": round(_deterministic_value(seed + "stability", 0.0, 0.2), 5),
                        "raw": {
                            "demo_record": True,
                            "seed": seed,
                        },
                    }
                )

                if len(rows) >= limit:
                    return pd.DataFrame(rows)

    return pd.DataFrame(rows)


def demo_candidates_for_query(
    reaction: str,
    selected_sources: list[str],
    temperature_range: tuple[int, int],
    ph_range: tuple[float, float],
    limit: int = 60,
) -> pd.DataFrame:
    """Filter demo dataset by reaction keyword, source, and slider ranges.

    Args:
        reaction: Input reaction string.
        selected_sources: Selected source names.
        temperature_range: Inclusive temperature bounds in Kelvin.
        ph_range: Inclusive pH bounds.
        limit: Maximum output rows.

    Returns:
        Filtered DataFrame suitable for UI rendering.

    Raises:
        None.
    """
    df = build_demo_candidates(limit=300)
    if df.empty:
        return df

    if selected_sources:
        df = df[df["source"].isin(selected_sources)]

    query_tokens = [token.strip().lower() for token in reaction.replace("->", " ").replace("→", " ").split() if token.strip()]
    if query_tokens:
        token_pattern = "|".join(re.escape(token) for token in query_tokens[:4])
        matched = df[
            df["reaction"].astype(str).str.lower().str.contains(token_pattern, na=False)
            | df["formula"].astype(str).str.lower().str.contains(token_pattern, na=False)
        ]
        if not matched.empty:
            df = matched

    min_temp, max_temp = temperature_range
    min_ph, max_ph = ph_range
    df = df[
        df["conditions"].map(lambda c: min_temp <= int(c.get("temperature_k", 0)) <= max_temp)
        & df["conditions"].map(lambda c: min_ph <= float(c.get("ph", 0.0)) <= max_ph)
    ]

    if df.empty:
        return build_demo_candidates(limit=limit)

    return df.sort_values(by="activity_value", ascending=True).head(limit).reset_index(drop=True)
