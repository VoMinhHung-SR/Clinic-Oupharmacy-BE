import math
import time
from statistics import mean, median

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connections
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory

from storeApp.views import search_products


class Command(BaseCommand):
    help = "Benchmark store search endpoint latency and SQL query count."

    def add_arguments(self, parser):
        parser.add_argument("--iterations", type=int, default=20)
        parser.add_argument("--query", type=str, default="cảm cúm")
        parser.add_argument("--page-size", type=int, default=12)
        parser.add_argument("--sort", type=str, default="relevance")

    def handle(self, *args, **options):
        iterations = max(1, int(options["iterations"]))
        query = options["query"]
        page_size = max(1, int(options["page_size"]))
        sort = options["sort"]

        factory = APIRequestFactory()
        db_alias = "store" if "store" in settings.DATABASES else "default"
        db_connection = connections[db_alias]
        latencies_ms = []
        query_counts = []
        status_codes = {}

        self.stdout.write(
            f"Benchmarking GET /api/store/search (iterations={iterations}, q='{query}', page_size={page_size}, sort={sort})"
        )

        for _ in range(iterations):
            request = factory.get(
                "/api/store/search/",
                {"q": query, "page": 1, "page_size": page_size, "sort": sort},
            )
            started = time.perf_counter()
            original_force_debug = db_connection.force_debug_cursor
            db_connection.force_debug_cursor = True
            try:
                with CaptureQueriesContext(db_connection) as captured:
                    response = search_products(request)
            finally:
                db_connection.force_debug_cursor = original_force_debug
            elapsed_ms = (time.perf_counter() - started) * 1000

            latencies_ms.append(elapsed_ms)
            query_counts.append(len(captured))
            status_codes[response.status_code] = status_codes.get(response.status_code, 0) + 1

        sorted_latencies = sorted(latencies_ms)
        p95_index = max(0, math.ceil(0.95 * len(sorted_latencies)) - 1)
        p95 = sorted_latencies[p95_index]

        self.stdout.write("")
        self.stdout.write("Results:")
        self.stdout.write(f"- status codes: {status_codes}")
        self.stdout.write(f"- latency ms (min/median/mean/p95/max): {min(latencies_ms):.2f} / {median(latencies_ms):.2f} / {mean(latencies_ms):.2f} / {p95:.2f} / {max(latencies_ms):.2f}")
        self.stdout.write(f"- sql queries per request (min/mean/max): {min(query_counts)} / {mean(query_counts):.2f} / {max(query_counts)}")
