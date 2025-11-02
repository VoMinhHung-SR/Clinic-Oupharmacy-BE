class StoreRouter:
    """
    Database router để route các models của storeApp sang database 'store'
    và các models khác sang database 'default'
    """
    app_label = 'storeApp'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return 'store'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return 'store'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Cho phép relation giữa các objects, kể cả cross-database
        # Django sẽ tự xử lý việc lưu foreign key ID thay vì object
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.app_label:
            return db == 'store'
        # Các app khác chỉ migrate vào default
        if db == 'store':
            return False
        return True

