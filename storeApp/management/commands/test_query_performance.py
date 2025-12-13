"""
Management command để test query performance
Chạy: python manage.py test_query_performance
"""
from django.core.management.base import BaseCommand
from django.db import connection, reset_queries
from mainApp.models import MedicineUnit
import time


class Command(BaseCommand):
    help = 'Test query performance'

    def handle(self, *args, **options):
        self.stdout.write('🔍 Testing Query Performance...\n')
        
        # Test 1: Basic filter
        reset_queries()
        start_time = time.time()
        
        products = list(MedicineUnit.objects.filter(
            is_published=True
        )[:20])
        
        elapsed_time = time.time() - start_time
        queries = connection.queries
        
        self.stdout.write('📊 Test 1: Basic filter (is_published=True)')
        self.stdout.write(f'  ⏱️  Time: {elapsed_time:.3f}s')
        self.stdout.write(f'  📈 Queries: {len(queries)}')
        self.stdout.write(f'  📦 Results: {len(products)} products\n')
        
        # Test 2: With select_related
        reset_queries()
        start_time = time.time()
        
        products = list(MedicineUnit.objects.filter(
            is_published=True
        ).select_related('medicine', 'category')[:20])
        
        elapsed_time = time.time() - start_time
        queries = connection.queries
        
        self.stdout.write('📊 Test 2: With select_related (medicine, category)')
        self.stdout.write(f'  ⏱️  Time: {elapsed_time:.3f}s')
        self.stdout.write(f'  📈 Queries: {len(queries)}')
        self.stdout.write(f'  📦 Results: {len(products)} products\n')
        
        # Test 3: Price filter
        reset_queries()
        start_time = time.time()
        
        products = list(MedicineUnit.objects.filter(
            is_published=True,
            price_value__gte=100000,
            price_value__lte=1000000
        ).select_related('medicine', 'category')[:20])
        
        elapsed_time = time.time() - start_time
        queries = connection.queries
        
        self.stdout.write('📊 Test 3: Price filter (100k - 1M)')
        self.stdout.write(f'  ⏱️  Time: {elapsed_time:.3f}s')
        self.stdout.write(f'  📈 Queries: {len(queries)}')
        self.stdout.write(f'  📦 Results: {len(products)} products\n')
        
        # Test 4: Order by product_ranking
        reset_queries()
        start_time = time.time()
        
        products = list(MedicineUnit.objects.filter(
            is_published=True
        ).select_related('medicine', 'category').order_by('-product_ranking')[:20])
        
        elapsed_time = time.time() - start_time
        queries = connection.queries
        
        self.stdout.write('📊 Test 4: Order by product_ranking')
        self.stdout.write(f'  ⏱️  Time: {elapsed_time:.3f}s')
        self.stdout.write(f'  📈 Queries: {len(queries)}')
        self.stdout.write(f'  📦 Results: {len(products)} products\n')
        
        # Show sample queries
        if queries:
            self.stdout.write('📝 Sample Queries:')
            for i, query in enumerate(queries[:3], 1):
                sql = query['sql'][:150] + '...' if len(query['sql']) > 150 else query['sql']
                query_time = float(query['time']) if isinstance(query['time'], str) else query['time']
                self.stdout.write(f'  {i}. Time: {query_time:.3f}s')
                self.stdout.write(f'     SQL: {sql}\n')

