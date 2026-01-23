from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        """Initialize master database on server startup"""
        import os
        # Only run once during startup (not in reloader)
        if os.environ.get('RUN_MAIN') == 'true' or os.environ.get('RUN_MAIN') is None:
            try:
                from core.db_initializer import initialize_master_database
                initialize_master_database()
            except Exception as e:
                print(f"✗ Error initializing master database: {e}")
