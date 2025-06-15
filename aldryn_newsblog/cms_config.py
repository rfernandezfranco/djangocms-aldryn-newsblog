from cms.app_base import CMSAppConfig
from djangocms_versioning.datastructures import VersionableItem

# Import the content model and the (soon to be created) copy function
from .models import ArticleContent, article_content_copy # article_content_copy will be the copy fn

class NewsBlogCMSConfig(CMSAppConfig):
    djangocms_versioning_enabled = True
    versioning = [
        VersionableItem(
            content_model=ArticleContent,
            grouper_field_name='article_grouper', # The FK from ArticleContent to ArticleGrouper
            copy_function=article_content_copy,
            #grouper_model=ArticleGrouper # Not strictly needed if resolvable from content_model
        ),
    ]
    # We might need to add versioning_models to specify which apps' models are versioned here
    # if ArticleContent has FKs/M2Ms to models in other apps that are also versioned by djangocms-versioning
    # For now, let's assume only local models or non-versioned external models.
