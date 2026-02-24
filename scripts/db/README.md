# Database Management Scripts

Thư mục này chứa các script để quản lý database: backup, sync, restore.

## Cấu trúc

```
scripts/db/
├── config.sh          # File cấu hình chung (load env, colors, utilities)
├── backup.sh          # Backup từ container (cần psql/pg_dump trên máy)
├── backup-docker.sh   # Backup bằng Docker — 2 DB (default + store), không cần cài PostgreSQL
├── restore.sh         # Restore vào DB (cần psql trên máy)
├── restore-docker.sh  # Restore vào container bằng Docker (cặp với backup-docker)
├── fix-sequences.sql  # Đồng bộ sequence với max(id) (chạy tự động sau restore)
├── sync.sh                  # Đồng bộ Local -> Container (full schema+data)
├── sync-container-to-local.sh # Đồng bộ Container -> Local
├── sync_and_drop.sh         # Drop bảng container rồi sync (ghi đè sạch)
├── sync_existing_tables.sh  # Chỉ data, từng bảng (default DB)
├── db-manager.sh            # Script master
└── backups/                 # Thư mục backup (tự động tạo)
```

## Cài đặt

Tất cả các script đã được set executable. Nếu chưa, chạy:

```bash
chmod +x scripts/db/*.sh
```

## Sử dụng

### Cách 1: Sử dụng script master (Khuyến nghị)

```bash
# Từ thư mục gốc của project
./scripts/db/db-manager.sh <command> [options]
```

### Cách 2: Sử dụng trực tiếp từng script

```bash
cd scripts/db
./backup.sh
./sync.sh
./restore.sh <backup_file>
```

## Các lệnh

### 1. Backup

Backup **cả 2 database** (default + store) từ container DB.

**Cách 1 – Backup bằng Docker (khuyến nghị, không cần cài PostgreSQL trên máy):**

```bash
./scripts/db/db-manager.sh backup-docker
# hoặc trực tiếp
./scripts/db/backup-docker.sh
```

Tạo **1 file** chứa cả 2 DB (pg_dumpall):

```bash
./scripts/db/backup-docker.sh --all
```

**Cách 2 – Backup từ máy host (cần cài `psql`, `pg_dump`):**

```bash
./scripts/db/db-manager.sh backup
# hoặc
./scripts/db/backup.sh
```

Backup files lưu trong `scripts/db/backups/` (hoặc thư mục truyền vào):
- **2 file:** `oupharmacydb_YYYYMMDD_HHMMSS.sql.gz`, `oupharmacy_store_db_YYYYMMDD_HHMMSS.sql.gz`
- **1 file (khi dùng `--all`):** `all_databases_YYYYMMDD_HHMMSS.sql.gz`

#### Phòng drop nhầm data (backup + restore container)

1. **Backup định kỳ** (schema + data + records) — chỉ cần Docker:
   ```bash
   ./scripts/db/backup-docker.sh
   # hoặc: ./scripts/db/db-manager.sh backup-docker
   ```
   Tạo 2 file trong `backups/`: default DB và store DB. Có thể đặt cron (vd mỗi ngày).

2. **Khi bị xóa/drop nhầm data** — restore từ file backup vào container (không cần cài psql trên máy):
   ```bash
   # Restore từng DB (tên DB tự đoán theo tên file)
   ./scripts/db/restore-docker.sh backups/oupharmacydb_20251204_225103.sql.gz
   ./scripts/db/restore-docker.sh backups/oupharmacy_store_db_20251204_225103.sql.gz
   # hoặc chỉ định DB: restore-docker.sh <file> oupharmacydb
   ./scripts/db/db-manager.sh restore-docker backups/oupharmacydb_20251204_225103.sql.gz
   ```
   Sau restore, script tự chạy **fix-sequences** để tránh lỗi duplicate key khi INSERT.

3. **Xem danh sách backup:** `./scripts/db/db-manager.sh list-backups`

### 2. Sync

**Local → Container** (đồng bộ từ máy lên container):

```bash
./scripts/db/db-manager.sh sync
# hoặc với force mode (ghi đè dữ liệu cũ trên container)
./scripts/db/db-manager.sh sync --force
```

**Container → Local** (kéo dữ liệu từ container về máy, ví dụ sau khi chạy production trong Docker):

```bash
./scripts/db/db-manager.sh sync-container-to-local
# hoặc
./scripts/db/sync-container-to-local.sh
# force: ghi đè DB local
./scripts/db/sync-container-to-local.sh --force
```

**Drop rồi sync (ghi đè sạch container):**

```bash
./scripts/db/db-manager.sh sync-drop
# hoặc
./scripts/db/sync_and_drop.sh
```

Script sẽ: drop toàn bộ bảng trong 2 DB trên container → gọi `sync.sh` (full sync + fix-sequences).

**Chỉ cập nhật data cho bảng đã tồn tại** (default DB, data-only, từng bảng):

```bash
./scripts/db/sync_existing_tables.sh
```

Dùng khi schema trên container đã đúng, chỉ cần kéo data mới từ local cho các bảng có sẵn (không thay đổi schema, không sync store DB).

**Lưu ý:**
- Script sẽ tự động tạo target database nếu chưa tồn tại
- `--force` (sync / sync-container-to-local): dump dùng `--clean --if-exists` nên ghi đè schema/data đích
- Sync full (sync / sync-container-to-local / sync-drop) dump **toàn bộ** schema + data và chạy **fix-sequences**

### 3. Restore

**Restore vào container (Docker, không cần psql trên máy)** — khuyến nghị khi dùng backup-docker:

```bash
./scripts/db/restore-docker.sh backups/oupharmacydb_20251204_225103.sql.gz
./scripts/db/restore-docker.sh backups/oupharmacy_store_db_20251204_225103.sql.gz
# hoặc: ./scripts/db/db-manager.sh restore-docker <file> [database_name]
```

**Restore từ máy host** (cần cài `psql`):

```bash
./scripts/db/db-manager.sh restore backups/oupharmacydb_20251204_225103.sql.gz oupharmacydb
```

Sau khi restore, script tự chạy **fix-sequences** (đồng bộ sequence với `max(id)`) để tránh lỗi duplicate key khi INSERT.

### 4. List Backups

Xem danh sách các backup files:

```bash
./scripts/db/db-manager.sh list-backups
```

### 5. Status

Kiểm tra trạng thái kết nối database:

```bash
./scripts/db/db-manager.sh status
```

## Cấu hình

Các script tự động đọc cấu hình từ `.env.production` ở thư mục gốc:

### Database Credentials (Required)
- `DB_PG_USER` - PostgreSQL username (default: `postgres`)
- `DB_PG_PASSWORD` - PostgreSQL password (default: `yourPassword`)
- `DB_PG_NAME_DEFAULT` - Tên database mặc định (default: `your_db_default_name`)
- `DB_PG_NAME_STORE` - Tên database store (default: `your_db_store_name`)

### Connection Settings (Optional - có default values)
- `DB_LOCAL_HOST` - Local PostgreSQL host (default: `127.0.0.1`)
- `DB_LOCAL_PORT` - Local PostgreSQL port (default: `5432`)
- `DB_CONTAINER_HOST` - Container PostgreSQL host (default: `localhost`)
  - **Từ host machine**: Dùng `localhost` hoặc `127.0.0.1` (default)
  - **Từ trong container network**: Dùng service name như `db` (từ docker-compose.yml)
  - **Hoặc IP address khác**: Nếu cần kết nối từ network khác
- `DB_CONTAINER_PORT` - Container PostgreSQL port (default: `5433`)
  - **Từ host machine**: Dùng mapped port (default: `5433` từ docker-compose ports mapping)
  - **Từ trong container network**: Dùng internal port (thường là `5432`)

### Backup Settings (Optional)
- `DB_BACKUP_DIR` - Thư mục lưu backup files (default: `scripts/db/backups`)
- `DB_CONTAINER_NAME` - Tên container Postgres khi dùng backup-docker.sh (default: `postgres`)

**Lưu ý:** Tất cả các giá trị đều có default, nên bạn không cần phải set tất cả trong `.env.production`. Chỉ cần set những giá trị khác với default.

**Ví dụ cấu hình cho các trường hợp khác nhau:**

1. **Chạy scripts từ host machine (mặc định):**
   ```env
   DB_CONTAINER_HOST=localhost
   DB_CONTAINER_PORT=5433
   ```

2. **Chạy scripts từ trong container network:**
   ```env
   DB_CONTAINER_HOST=db
   DB_CONTAINER_PORT=5432
   ```

3. **Kết nối từ máy khác trong cùng network:**
   ```env
   DB_CONTAINER_HOST=192.168.1.100
   DB_CONTAINER_PORT=5433
   ```

## Yêu cầu

- **backup-docker.sh / restore-docker.sh:** chỉ cần Docker (và container postgres đang chạy), không cần cài PostgreSQL trên máy.
- **backup.sh / sync / restore:** cần PostgreSQL client (`psql`, `pg_dump`) trên máy.
- Docker và Docker Compose (để chạy container database).
- Bash shell.

## Troubleshooting

### Lỗi kết nối database

1. Kiểm tra containers đang chạy:
   ```bash
   docker-compose ps
   ```

2. Kiểm tra kết nối:
   ```bash
   ./scripts/db/db-manager.sh status
   ```

3. Khởi động containers nếu cần:
   ```bash
   docker-compose up -d
   ```

### Lỗi permission

Đảm bảo các script có quyền thực thi:
```bash
chmod +x scripts/db/*.sh
```

### Lỗi không tìm thấy .env.production

Đảm bảo file `.env.production` tồn tại ở thư mục gốc của project.

## Best Practices

1. **Backup định kỳ** (phòng drop nhầm data): dùng backup-docker, có thể cron:
   ```bash
   ./scripts/db/backup-docker.sh
   ```
2. **Luôn backup trước khi sync/restore:**
   ```bash
   ./scripts/db/db-manager.sh backup-docker
   ./scripts/db/db-manager.sh sync
   ```

3. **Kiểm tra status trước khi thao tác:**
   ```bash
   ./scripts/db/db-manager.sh status
   ```

4. **Sử dụng script master (`db-manager.sh`) để dễ nhớ lệnh**

5. **Backup files được tự động compress để tiết kiệm dung lượng**

