"""In-process runners for catalog_import commands (no extra CLI wrappers)."""

from __future__ import annotations

from storeApp.management.commands._command_group import invoke_subcommand

from .store_import_csv import (
    DEFAULT_BATCH_COUNT,
    DEFAULT_BATCH_PACK_MULT_MAX,
    DEFAULT_BATCH_PACK_MULT_MIN,
    DEFAULT_STOCK,
    Command as ImportCsvCommand,
)

# Defaults when invoked in-process (import-refactor, store_reset_catalog, …).
IMPORT_CSV_DEFAULTS = {
    "dry_run": False,
    "update_existing": False,
    "no_batches": False,
    "default_stock": DEFAULT_STOCK,
    "batch_pack_mult_min": DEFAULT_BATCH_PACK_MULT_MIN,
    "batch_pack_mult_max": DEFAULT_BATCH_PACK_MULT_MAX,
    "batch_count": DEFAULT_BATCH_COUNT,
    "no_smart_random_price": False,
}


def run_import_csv(path, **options) -> None:
    merged = {**IMPORT_CSV_DEFAULTS, **options}
    invoke_subcommand(ImportCsvCommand, path=path, **merged)
