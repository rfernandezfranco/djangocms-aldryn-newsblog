from cms.app_base import CMSAppConfig

try:
    from djangocms_versioning.datastructures import VersionableItem
except ImportError:  # pragma: no cover - versioning optional
    VersionableItem = None

# Import the content model and the (soon to be created) copy function
from .models import ArticleContent, article_content_copy  # article_content_copy will be the copy fn


class NewsBlogCMSConfig(CMSAppConfig):
    djangocms_versioning_enabled = bool(VersionableItem)
    versioning = []
    if VersionableItem:
        versioning = [
            VersionableItem(
                content_model=ArticleContent,
                grouper_field_name='article_grouper',
                copy_function=article_content_copy,
            ),
        ]
    # We might need to add versioning_models to specify which apps' models are versioned here
    # if ArticleContent has FKs/M2Ms to models in other apps that are also versioned by djangocms-versioning
    # For now, let's assume only local models or non-versioned external models.
