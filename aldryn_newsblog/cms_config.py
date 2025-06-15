from cms.app_base import CMSAppConfig

from djangocms_versioning.datastructures import VersionableItem, default_copy

from .models import Article


class NewsBlogVersioningConfig(CMSAppConfig):
    djangocms_versioning_enabled = True
    versioning = [
        VersionableItem(
            content_model=Article.translations.model,
            grouper_field_name="master",
            extra_grouping_fields=["language_code"],
            copy_function=default_copy,
        )
    ]
