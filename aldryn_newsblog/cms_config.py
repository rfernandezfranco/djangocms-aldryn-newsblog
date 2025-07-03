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

        # Parler provides a dynamically generated translation model which
        # stores the language-dependent fields. This translation model has a
        # ``master`` ForeignKey back to :class:`Article`, which can be used as
        # the grouper field required by djangocms-versioning.
        ArticleTranslation = Article._parler_meta.root_model

        versioning = [
            VersionableItem(
                content_model=ArticleTranslation,
                grouper_field_name="master",
                copy_function=default_copy,
            )
        ]
