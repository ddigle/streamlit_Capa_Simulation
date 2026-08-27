"""Shared Core Data preparation path for CSV and internal database providers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataBatch,
    CoreDataProvider,
    normalize_core_data,
)
from capa_simulation.services.reference_transformer import build_reference_tables


@dataclass(frozen=True)
class PreparedCoreDataset:
    """One normalized source snapshot and its 16 derived reference tables."""

    batch: CoreDataBatch
    source_data: pd.DataFrame
    reference_tables: dict[str, pd.DataFrame]


def prepare_core_data_dataset(
    batch: CoreDataBatch,
    display_order: pd.DataFrame,
) -> PreparedCoreDataset:
    """Normalize, validate, and transform a provider result without CSV coupling."""
    normalized = normalize_core_data(batch.frame)
    reference_tables = build_reference_tables(normalized, display_order)
    return PreparedCoreDataset(
        batch=batch,
        source_data=normalized,
        reference_tables=reference_tables,
    )


def fetch_core_data_dataset(
    provider: CoreDataProvider,
    simulation_code: str,
    display_order: pd.DataFrame,
) -> PreparedCoreDataset:
    """Fetch a simulation code and send it through the common preparation path."""
    return prepare_core_data_dataset(provider.fetch(simulation_code), display_order)
