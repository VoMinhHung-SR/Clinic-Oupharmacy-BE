"""
Store catalog CLI — import CSV/JSON, refactor workflow, product audit.

Usage:
  python manage.py store_catalog import-csv [path] [--dry-run] ...
  python manage.py store_catalog import-refactor [--dry-run] [--apply] ...
  python manage.py store_catalog audit --overview
"""

from storeApp.management.commands._command_group import build_group_command
from storeApp.management.commands.catalog_import.store_audit_product import Command as AuditCommand
from storeApp.management.commands.catalog_import.store_import_csv import Command as ImportCsvCommand
from storeApp.management.commands.catalog_import.store_import_refactor import Command as ImportRefactorCommand

Command = build_group_command(
    help_text="Catalog import & audit (import-csv | import-refactor | audit).",
    subcommands={
        "import-csv": ImportCsvCommand,
        "import-refactor": ImportRefactorCommand,
        "audit": AuditCommand,
    },
)
