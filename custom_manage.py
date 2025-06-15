#!/usr/bin/env python
import os
import sys
from django.conf import settings

if __name__ == "__main__":
    # Directly configure settings here using HELPER_SETTINGS from test_settings
    # This avoids relying on DJANGO_SETTINGS_MODULE import order issues with configure()
    try:
        from test_settings import HELPER_SETTINGS
        # Ensure critical apps are present, in case test_settings.py was reverted
        # or if HELPER_SETTINGS is too minimal by default.
        essential_apps = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.admin',
            'django.contrib.sites',
            'django.contrib.staticfiles',
            'django.contrib.messages',
            'cms',
            'menus',
            'parler', # Often a core dependency for translated models
            'taggit', # Was in original HELPER_SETTINGS, seems important
            'filer',  # Was in original HELPER_SETTINGS
            'aldryn_newsblog',
        ]
        # Merge and ensure no duplicates, keeping essential_apps prioritized
        # by putting them at the end if not already present.
        existing_apps = set(HELPER_SETTINGS.get('INSTALLED_APPS', []))
        for app in essential_apps:
            if app not in existing_apps:
                HELPER_SETTINGS.setdefault('INSTALLED_APPS', []).append(app)

        if not settings.configured:
            settings.configure(**HELPER_SETTINGS)
        import django
        django.setup() # Call setup once here after configuring.
    except ImportError as e:
        raise ImportError(
            f"Failed to import or configure settings from test_settings: {e}. "
            "Ensure test_settings.py and its HELPER_SETTINGS are correct."
        ) from e

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
