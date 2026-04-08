"""
Database router: mỗi app chỉ migrate trên đúng DB.
- storeApp → DB alias STORE_DATABASE_ALIAS
- Các app khác → DB 'default'
"""
from storeApp.constants import STORE_DATABASE_ALIAS

STORE_APP_LABEL = "storeapp"  # so sánh không phân biệt hoa thường


class StoreRouter:
    def _is_store_app(self, app_label):
        return (app_label or "").strip().lower() == STORE_APP_LABEL

    def db_for_read(self, model, **hints):
        return STORE_DATABASE_ALIAS if self._is_store_app(model._meta.app_label) else None

    def db_for_write(self, model, **hints):
        return STORE_DATABASE_ALIAS if self._is_store_app(model._meta.app_label) else None

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if self._is_store_app(app_label):
            return db == STORE_DATABASE_ALIAS
        return db != STORE_DATABASE_ALIAS
