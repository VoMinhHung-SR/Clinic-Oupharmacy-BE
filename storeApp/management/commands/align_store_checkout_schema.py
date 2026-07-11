"""
Align legacy store checkout tables with current models (store DB only).

Why: Docker staging dumps can retain `medicine_unit_id` on store_order_item /
store_medicine_batch while models expect product_variant(_unit)_id — guest
checkout then 500s on OrderItem insert. Stock code already falls back to
ProductVariant.in_stock when batch schema drifts.

Safety:
- Uses database alias `store` only — never touches default/mainApp.
- ADDs missing columns; does NOT DROP `medicine_unit_id` (legacy / no prescribe impact).
- Does NOT rewrite mainApp PrescriptionDetail or MedicineUnit.
"""

from django.core.management.base import BaseCommand
from django.db import connections, transaction


STORE_ALIAS = "store"


class Command(BaseCommand):
    help = (
        "Add product_variant(_unit)_id (+ batch import_price_per_base_unit) on "
        "store checkout tables if missing. Store DB only; keeps medicine_unit_id."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned SQL without executing",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        conn = connections[STORE_ALIAS]
        statements = self._plan(conn)
        if not statements:
            self.stdout.write(self.style.SUCCESS("Store checkout schema already aligned."))
            return

        self.stdout.write(f"Planned {len(statements)} statement(s) on alias={STORE_ALIAS}:")
        for sql in statements:
            self.stdout.write(f"  {sql}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run — no changes applied."))
            return

        with transaction.atomic(using=STORE_ALIAS):
            with conn.cursor() as cursor:
                for sql in statements:
                    cursor.execute(sql)

        self.stdout.write(self.style.SUCCESS("Store checkout schema aligned (medicine_unit_id kept)."))

    def _plan(self, conn) -> list[str]:
        statements: list[str] = []
        cols_order_item = self._columns(conn, "store_order_item")
        cols_batch = self._columns(conn, "store_medicine_batch")

        if "product_variant_id" not in cols_order_item:
            statements.append(
                "ALTER TABLE store_order_item "
                "ADD COLUMN product_variant_id bigint NULL"
            )
        if "product_variant_unit_id" not in cols_order_item:
            statements.append(
                "ALTER TABLE store_order_item "
                "ADD COLUMN product_variant_unit_id bigint NULL"
            )
        # Legacy column: keep for old rows, allow NULL so new OrderItem inserts work
        if self._column_is_not_null(conn, "store_order_item", "medicine_unit_id"):
            statements.append(
                "ALTER TABLE store_order_item "
                "ALTER COLUMN medicine_unit_id DROP NOT NULL"
            )

        if "product_variant_id" not in cols_batch:
            statements.append(
                "ALTER TABLE store_medicine_batch "
                "ADD COLUMN product_variant_id bigint NULL"
            )
        if "import_price_per_base_unit" not in cols_batch:
            statements.append(
                "ALTER TABLE store_medicine_batch "
                "ADD COLUMN import_price_per_base_unit numeric(12, 2) NULL"
            )
            if "import_price" in cols_batch:
                statements.append(
                    "UPDATE store_medicine_batch "
                    "SET import_price_per_base_unit = import_price::numeric "
                    "WHERE import_price IS NOT NULL AND import_price_per_base_unit IS NULL"
                )
        if self._column_is_not_null(conn, "store_medicine_batch", "medicine_unit_id"):
            statements.append(
                "ALTER TABLE store_medicine_batch "
                "ALTER COLUMN medicine_unit_id DROP NOT NULL"
            )

        # FKs after columns exist (idempotent by constraint name). NULL legacy rows OK.
        will_have_oi_pv = "product_variant_id" in cols_order_item or any(
            "store_order_item ADD COLUMN product_variant_id" in s for s in statements
        )
        will_have_oi_pvu = "product_variant_unit_id" in cols_order_item or any(
            "store_order_item ADD COLUMN product_variant_unit_id" in s for s in statements
        )
        will_have_batch_pv = "product_variant_id" in cols_batch or any(
            "store_medicine_batch ADD COLUMN product_variant_id" in s for s in statements
        )

        if will_have_oi_pv and not self._constraint_exists(conn, "store_order_item_product_variant_id_fk"):
            statements.append(
                "ALTER TABLE store_order_item "
                "ADD CONSTRAINT store_order_item_product_variant_id_fk "
                "FOREIGN KEY (product_variant_id) REFERENCES store_product_variant(id) "
                "DEFERRABLE INITIALLY DEFERRED"
            )
        if will_have_oi_pvu and not self._constraint_exists(
            conn, "store_order_item_product_variant_unit_id_fk"
        ):
            pvu_table = self._product_variant_unit_table(conn)
            if pvu_table:
                statements.append(
                    "ALTER TABLE store_order_item "
                    "ADD CONSTRAINT store_order_item_product_variant_unit_id_fk "
                    f'FOREIGN KEY (product_variant_unit_id) REFERENCES "{pvu_table}"(id) '
                    "DEFERRABLE INITIALLY DEFERRED"
                )
        if will_have_batch_pv and not self._constraint_exists(
            conn, "store_medicine_batch_product_variant_id_fk"
        ):
            statements.append(
                "ALTER TABLE store_medicine_batch "
                "ADD CONSTRAINT store_medicine_batch_product_variant_id_fk "
                "FOREIGN KEY (product_variant_id) REFERENCES store_product_variant(id) "
                "DEFERRABLE INITIALLY DEFERRED"
            )

        return statements

    def _columns(self, conn, table: str) -> set[str]:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                """,
                [table],
            )
            return {row[0] for row in cursor.fetchall()}

    def _column_is_not_null(self, conn, table: str, column: str) -> bool:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
                """,
                [table, column],
            )
            row = cursor.fetchone()
            return bool(row) and row[0] == "NO"

    def _constraint_exists(self, conn, name: str) -> bool:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema = 'public' AND constraint_name = %s
                """,
                [name],
            )
            return cursor.fetchone() is not None

    def _product_variant_unit_table(self, conn) -> str | None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('store_product_variant_unit', 'storeApp_productvariantunit')
                ORDER BY CASE table_name
                    WHEN 'store_product_variant_unit' THEN 0
                    ELSE 1
                END
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            return row[0] if row else None
