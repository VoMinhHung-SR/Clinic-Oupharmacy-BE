# backfill

Backfill dữ liệu store / mainApp. CLI entry: `../store_backfill.py`.

```bash
python manage.py store_backfill unit-prices [--dry-run] [--database=store]
python manage.py store_backfill medicine-unit-stats [--dry-run]
```

| File | Vai trò |
|------|---------|
| `backfill_store_unit_prices.py` | Điền `ProductVariantUnit.price_value` khi = 0 |
| `backfill_medicine_unit_stats.py` | Tạo `MedicineUnitStats` cho unit chưa có stats |
