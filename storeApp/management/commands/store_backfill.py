"""
Store DB backfill helpers.

Usage:
  python manage.py store_backfill unit-prices [--dry-run] ...
  python manage.py store_backfill medicine-unit-stats [--dry-run]
"""

from storeApp.management.commands._command_group import build_group_command
from storeApp.management.commands.backfill.backfill_medicine_unit_stats import (
    Command as MedicineUnitStatsCommand,
)
from storeApp.management.commands.backfill.backfill_store_unit_prices import (
    Command as StoreUnitPricesCommand,
)

Command = build_group_command(
    help_text="Store backfills (unit-prices | medicine-unit-stats).",
    subcommands={
        "unit-prices": StoreUnitPricesCommand,
        "medicine-unit-stats": MedicineUnitStatsCommand,
    },
)
