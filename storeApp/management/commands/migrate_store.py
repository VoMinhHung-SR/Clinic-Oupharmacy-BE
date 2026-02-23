"""
Migrate chỉ app storeApp trên DB 'store'.
Dùng khi cần kiểm soát: chỉ apply migrations của storeApp lên oupharmacy_store_db.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Migrate storeApp only on DB 'store'. Same as: migrate storeApp --database=store"

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)
        call_command("migrate", "storeApp", "--database=store", verbosity=verbosity)
