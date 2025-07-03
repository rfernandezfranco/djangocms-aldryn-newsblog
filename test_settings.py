#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys
import importlib

from django import get_version
from django.utils import encoding as django_encoding

from cms import __version__ as cms_string_version

from looseversion import LooseVersion


django_version = LooseVersion(get_version())
cms_version = LooseVersion(cms_string_version)

# Compatibility for packages still importing force_text from Django 5
if not hasattr(django_encoding, "force_text"):
    django_encoding.force_text = django_encoding.force_str

try:
    importlib.import_module("django.utils.six")  # pragma: no cover - used by old libs
except Exception:  # pragma: no cover - fallback for Django>=3
    import six
    sys.modules["django.utils.six"] = six
    sys.modules["django.utils.six.moves"] = six.moves

try:
    import django.conf.urls
    from django.urls import re_path

    if not hasattr(django.conf.urls, "url"):
        django.conf.urls.url = re_path
except Exception:
    pass

# Alias djangocms_text for backwards compatibility

try:
    importlib.import_module("djangocms_text")
except ModuleNotFoundError:  # pragma: no cover - alias when module not present
    try:
        text_mod = importlib.import_module("djangocms_text_ckeditor")
        sys.modules["djangocms_text"] = text_mod
        try:
            from djangocms_text_ckeditor.apps import TextCkeditorConfig

            TextCkeditorConfig.label = "djangocms_text"
        except Exception:  # pragma: no cover - app label may not exist
            pass
        # plugin compatibility handled after Django setup
    except Exception:
        pass


def patch_text_plugin():
    try:
        from djangocms_text_ckeditor.models import Text

        if not hasattr(Text, "djangocms_text_text"):
            Text.djangocms_text_text = property(lambda self: self)
    except Exception:
        pass
    try:
        from cms.models.pluginmodel import CMSPlugin

        if not hasattr(CMSPlugin, "djangocms_text_text"):
            if hasattr(CMSPlugin, "djangocms_text_ckeditor_text"):
                CMSPlugin.djangocms_text_text = property(
                    lambda self: self.djangocms_text_ckeditor_text
                )
            else:  # pragma: no cover - fallback to plugin instance
                CMSPlugin.djangocms_text_text = property(
                    lambda self: self.get_plugin_instance()[0]
                )
    except Exception:
        pass


HELPER_SETTINGS = {
    'TIME_ZONE': 'Europe/Zurich',
    'SECRET_KEY': 'not-so-secret',
    'INSTALLED_APPS': [
        'djangocms_alias',
        'djangocms_versioning',
        'aldryn_apphooks_config',
        'aldryn_categories',
        'aldryn_people',
        'aldryn_translation_tools',
        'djangocms_text',
        'easy_thumbnails',
        'filer',
        'mptt',
        'parler',
        'sortedm2m',
        'taggit',
        'aldryn_common',
    ],
    'TEMPLATE_DIRS': (
        os.path.join(
            os.path.dirname(__file__),
            'aldryn_newsblog', 'tests', 'templates'),
    ),
    'ALDRYN_NEWSBLOG_TEMPLATE_PREFIXES': [('dummy', 'dummy'), ],
    'CMS_CONFIRM_VERSION4': True,
    'CMS_PERMISSION': True,
    # 'CMS_CONFIRM_VERSION4': True,
    'SITE_ID': 1,
    'LANGUAGES': (
        ('en', 'English'),
        ('de', 'German'),
        ('fr', 'French'),
    ),
    'CMS_LANGUAGES': {
        1: [
            {
                'code': 'en',
                'name': 'English',
                'fallbacks': ['de', 'fr', ]
            },
            {
                'code': 'de',
                'name': 'Deutsche',
                'fallbacks': ['en', ]  # FOR TESTING DO NOT ADD 'fr' HERE
            },
            {
                'code': 'fr',
                'name': 'Française',
                'fallbacks': ['en', ]  # FOR TESTING DO NOT ADD 'de' HERE
            },
            {
                'code': 'it',
                'name': 'Italiano',
                'fallbacks': ['fr', ]  # FOR TESTING, LEAVE AS ONLY 'fr'
            },
        ],
        'default': {
            'redirect_on_fallback': True,  # PLEASE DO NOT CHANGE THIS
        }
    },
    # app-specific
    'PARLER_LANGUAGES': {
        1: [
            {
                'code': 'en',
                'fallbacks': ['de', ],
            },
            {
                'code': 'de',
                'fallbacks': ['en', ],
            },
        ],
        'default': {
            'code': 'en',
            'fallbacks': ['en'],
            'hide_untranslated': False
        }
    },
    #
    # NOTE: The following setting `PARLER_ENABLE_CACHING = False` is required
    # for tests to pass.
    #
    # There appears to be a bug in Parler which leaves translations in Parler's
    # cache even after the parent object has been deleted. In production
    # environments, this is unlikely to affect anything, because newly created
    # objects will have new IDs. In testing, new objects are created with IDs
    # that were previously used, which reveals this issue.
    #
    'PARLER_ENABLE_CACHING': False,
    'ALDRYN_SEARCH_DEFAULT_LANGUAGE': 'en',
    'HAYSTACK_CONNECTIONS': {
        'default': {
            'ENGINE': 'haystack.backends.simple_backend.SimpleEngine',
        },
        'de': {
            'ENGINE': 'haystack.backends.simple_backend.SimpleEngine',
        },
    },
    'THUMBNAIL_HIGH_RESOLUTION': True,
    'THUMBNAIL_PROCESSORS': (
        'easy_thumbnails.processors.colorspace',
        'easy_thumbnails.processors.autocrop',
        # 'easy_thumbnails.processors.scale_and_crop',
        'filer.thumbnail_processors.scale_and_crop_with_subject_location',
        'easy_thumbnails.processors.filters',
    ),
    # 'DATABASES': {
    #     'default': {
    #         'ENGINE': 'django.db.backends.sqlite3',
    #         'NAME': 'mydatabase',
    #     },
    #     'mysql': {
    #         'ENGINE': 'django.db.backends.mysql',
    #         'NAME': 'newsblog_test',
    #         'USER': 'root',
    #         'PASSWORD': '',
    #         'HOST': '',
    #         'PORT': '3306',
    #     },
    #     'postgres': {
    #         'ENGINE': 'django.db.backends.postgresql_psycopg2',
    #         'NAME': 'newsblog_test',
    #         'USER': 'test',
    #         'PASSWORD': '',
    #         'HOST': '127.0.0.1',
    #         'PORT': '5432',
    #     }
    # }
    # This set of MW classes should work for Django 1.6 and 1.7.
    'MIDDLEWARE': [
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.locale.LocaleMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        # NOTE: This will actually be removed below in CMS<3.2 installs.
        'cms.middleware.utils.ApphookReloadMiddleware',
        'cms.middleware.user.CurrentUserMiddleware',
        'cms.middleware.page.CurrentPageMiddleware',
        'cms.middleware.toolbar.ToolbarMiddleware',
        'cms.middleware.language.LanguageCookieMiddleware'
    ]
}


def boolean_ish(var):
    var = '{}'.format(var)
    var = var.lower()
    if var in ('false', 'nope', '0', 'none', 'no'):
        return False
    else:
        return bool(var)


def run():
    from djangocms_helper import runner

    # --boilerplate option will ensure correct boilerplate settings are
    # added to settings
    extra_args = sys.argv[1:] if len(sys.argv) > 1 else []
    runner.cms('aldryn_newsblog', [sys.argv[0]], extra_args=extra_args)
    patch_text_plugin()


if __name__ == "__main__":
    run()
