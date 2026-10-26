class MovilRouter:
    """La aplicación móvil nunca lee ni migra las bases del sistema original."""

    def db_for_read(self, model, **hints):
        return "movil" if model._meta.app_label == "movil" else None

    def db_for_write(self, model, **hints):
        return "movil" if model._meta.app_label == "movil" else None

    def allow_relation(self, obj1, obj2, **hints):
        if "movil" in (obj1._meta.app_label, obj2._meta.app_label):
            return obj1._meta.app_label == obj2._meta.app_label == "movil"
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == "movil":
            return db == "movil"
        if db == "movil":
            return False
        return None
