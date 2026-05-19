"""In-process runners for catalog_import commands (no extra CLI wrappers)."""

from __future__ import annotations

from storeApp.management.commands._command_group import invoke_subcommand

from .store_import_csv import Command as ImportCsvCommand


def run_import_csv(path, **options) -> None:
    invoke_subcommand(ImportCsvCommand, path=path, **options)
