from django.template.response import TemplateResponse
from .utils import add_prefix_to_path
def render_article_content(request, article):
    template = add_prefix_to_path(
        'aldryn_newsblog/article_preview.html', article.app_config.template_prefix
    ) if (
        hasattr(article, 'app_config') and article.app_config.template_prefix
    ) else 'aldryn_newsblog/article_preview.html'
    context = {'article': article}
    return TemplateResponse(request, template, context)
