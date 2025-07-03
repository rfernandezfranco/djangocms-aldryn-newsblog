from cms.app_base import CMSAppConfig
from django.template.response import TemplateResponse

try:
    from djangocms_versioning.datastructures import VersionableItem
except ImportError:  # pragma: no cover - versioning optional
    VersionableItem = None

# Import the content model and the (soon to be created) copy function
from .models import ArticleContent, article_content_copy  # article_content_copy will be the copy fn


def render_articlecontent(request, obj):
    """Render the given ArticleContent for admin previews."""
    template = getattr(obj, 'preview_template', 'aldryn_newsblog/article_detail.html')
    context = {
        'article': obj,
        'object': obj,
    }
    namespace = None
    if getattr(obj, 'article_grouper_id', None):
        try:
            namespace = obj.article_grouper.app_config.namespace
        except Exception:
            namespace = None
    return TemplateResponse(request, template, context, current_app=namespace)


class NewsBlogCMSConfig(CMSAppConfig):
    djangocms_versioning_enabled = bool(VersionableItem)
    # Enable django CMS integration so that articles can be previewed and edited
    # through the CMS toolbar. The cms_toolbar_enabled_models attribute tells
    # django CMS which models provide frontend rendering support.
    cms_enabled = True
    cms_toolbar_enabled_models = [
        (ArticleContent, render_articlecontent, 'article_grouper'),
    ]
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
