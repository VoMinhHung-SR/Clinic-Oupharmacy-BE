"""
Align PostgreSQL sequences with current MAX(id) for storeApp models.

Use after pg_restore / COPY / bulk insert with explicit IDs so new rows do not
hit duplicate primary key errors (sequence still at 1 while rows use large ids).

  STORE_DATABASE_URL_PG=postgresql://.../store_db python manage.py reset_store_sequences
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connections

from storeApp.constants import STORE_DATABASE_ALIAS


class Command(BaseCommand):
    help = (
        f"Reset PostgreSQL sequences for storeApp models (default DB alias: {STORE_DATABASE_ALIAS}). "
        "Run after restoring store data from another environment."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=STORE_DATABASE_ALIAS,
            help=f"Django database alias (default: {STORE_DATABASE_ALIAS})",
        )

    def handle(self, *args, **options):
        db = options["database"]
        connection = connections[db]
        if connection.vendor != "postgresql":
            self.stderr.write(
                self.style.WARNING(
                    f"Database '{db}' is not PostgreSQL; sequence reset skipped."
                )
            )
            return

        app_config = apps.get_app_config("storeApp")
        models = list(app_config.get_models())
        sql_list = connection.ops.sequence_reset_sql(no_style(), models)
        if not sql_list:
            self.stdout.write(
                "No sequence reset SQL generated (empty tables or no serial columns)."
            )
            return

        with connection.cursor() as cursor:
            for sql in sql_list:
                cursor.execute(sql)

        self.stdout.write(
            self.style.SUCCESS(
                f"Executed {len(sql_list)} sequence reset statement(s) on database '{db}'."
            )
        )