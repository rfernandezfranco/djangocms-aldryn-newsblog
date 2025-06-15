#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

from django import get_version

from cms import __version__ as cms_string_version

from looseversion import LooseVersion


django_version = LooseVersion(get_version())
cms_version = LooseVersion(cms_string_version)

HELPER_SETTINGS = {
    'TIME_ZONE': 'Europe/Zurich',
    'INSTALLED_APPS': [
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.admin',
        'django.contrib.sites',
        'django.contrib.staticfiles',
        'django.contrib.messages',
        'menus',  # Added menus app for Django CMS
        'treebeard', # Added treebeard for Django CMS
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
        'cms',  # Added Django CMS
        'aldryn_newsblog', # Added the app itself
    ],
    'STATIC_URL': '/static/', # Added STATIC_URL
    'STATIC_ROOT': os.path.join(os.path.dirname(__file__), 'staticfiles_collected'), # Added STATIC_ROOT
    'MEDIA_URL': '/media/', # Often needed too
    'MEDIA_ROOT': os.path.join(os.path.dirname(__file__), 'media'), # Often needed too
    'TEMPLATES': [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [
                os.path.join(os.path.dirname(__file__), 'aldryn_newsblog', 'tests', 'templates'),
            ],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request', # Required by CMS
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                    'django.template.context_processors.i18n',
                    'cms.context_processors.cms_settings',
                ],
            },
        },
    ],
    # 'TEMPLATE_DIRS': (...) # This is now incorporated into TEMPLATES above
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
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:', # Use in-memory SQLite
        }
    },
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

# Ensure settings are configured when test_settings.py is imported as a module
from django.conf import settings
if not settings.configured:
    settings.configure(**HELPER_SETTINGS)
# import django # django.setup() should be called by the management command utility
# django.setup() # Removed to prevent reentrancy error


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


if __name__ == "__main__":
    run()
