from cms.app_base import CMSAppConfig
from django.conf import settings

from aldryn_newsblog.models import Article


class NewsBlogCMSConfig(CMSAppConfig):
    djangocms_versioning_enabled = getattr(
        settings, "ALDRYN_NEWSBLOG_VERSIONING_ENABLED", False
    )
    cms_enabled = True

    if djangocms_versioning_enabled:
        from djangocms_versioning.datastructures import VersionableItem, default_copy

        versioning = [
            VersionableItem(
                content_model=Article,
                grouper_field_name="id",
                copy_function=default_copy,
            )
        ]
