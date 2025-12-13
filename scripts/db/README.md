# Database Management Scripts

Thư mục này chứa các script để quản lý database: backup, sync, restore.

## Cấu trúc

```
scripts/db/
├── config.sh          # File cấu hình chung (load env, colors, utilities)
├── backup.sh          # Backup databases từ container
├── sync.sh            # Đồng bộ databases từ local sang container
├── restore.sh         # Restore database từ backup file
├── db-manager.sh      # Script master để quản lý tất cả
└── backups/           # Thư mục chứa các file backup (tự động tạo)
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

Backup tất cả databases từ container:

```bash
./scripts/db/db-manager.sh backup
# hoặc
./scripts/db/backup.sh
```

Backup files sẽ được lưu trong `scripts/db/backups/` với format:
- `oupharmacydb_YYYYMMDD_HHMMSS.sql.gz`
- `oupharmacy_store_db_YYYYMMDD_HHMMSS.sql.gz`

### 2. Sync

Đồng bộ databases từ local PostgreSQL sang container:

```bash
./scripts/db/db-manager.sh sync
# hoặc với force mode (xóa dữ liệu cũ)
./scripts/db/db-manager.sh sync --force
```

**Lưu ý:**
- Script sẽ tự động tạo target database nếu chưa tồn tại
- `--force` sẽ drop và recreate database (mất dữ liệu cũ)

### 3. Restore

Restore database từ backup file:

```bash
./scripts/db/db-manager.sh restore backups/oupharmacydb_20251204_225103.sql.gz
# hoặc chỉ định database name
./scripts/db/db-manager.sh restore backups/oupharmacydb_20251204_225103.sql.gz oupharmacydb
```

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

- PostgreSQL client tools (`psql`, `pg_dump`, `pg_restore`)
- Docker và Docker Compose (để chạy container database)
- Bash shell

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

1. **Luôn backup trước khi sync/restore:**
   ```bash
   ./scripts/db/db-manager.sh backup
   ./scripts/db/db-manager.sh sync
   ```

2. **Kiểm tra status trước khi thao tác:**
   ```bash
   ./scripts/db/db-manager.sh status
   ```

3. **Sử dụng script master (`db-manager.sh`) để dễ nhớ lệnh**

4. **Backup files được tự động compress để tiết kiệm dung lượng**

