"""
Database router: mỗi app chỉ migrate trên đúng DB.
- storeApp → DB 'store'
- Các app khác → DB 'default'
"""
STORE_APP_LABEL = "storeapp"  # so sánh không phân biệt hoa thường


class StoreRouter:
    def _is_store_app(self, app_label):
        return (app_label or "").strip().lower() == STORE_APP_LABEL

    def db_for_read(self, model, **hints):
        return "store" if self._is_store_app(model._meta.app_label) else None

    def db_for_write(self, model, **hints):
        return "store" if self._is_store_app(model._meta.app_label) else None

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == "store" if self._is_store_app(app_label) else db != "store"
