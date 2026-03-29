# Scripts (BE)

**Cổng chính cho thao tác PostgreSQL (backup, sync hai DB, dump/restore chỉ store):**

```bash
./scripts/db/db-manager.sh help
```

| Nhu cầu | Lệnh gợi ý |
|--------|------------|
| Full local → container (default + store) | `db-manager.sh sync` |
| Drop sạch schema container rồi full sync | `db-manager.sh sync-drop` |
| Chỉ dump/restore **data** DB store | `db-manager.sh store-dump` / `store-restore` |
| Chi tiết | `scripts/db/README.md` |
