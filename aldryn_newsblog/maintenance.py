"""
Add into settings:

HEALTHCHECK_FUNCTIONS = [
    "aldryn_newsblog.maintenance.healthcheck",
    ...
]
"""
from django.http import HttpRequest

from .cms_appconfig import NewsBlogConfig
from .models import ArticleContent, ArticleGrouper # Changed Article


def healthcheck(request: HttpRequest, *args, **kwargs) -> None:
    """Checking that the system is functional."""
    ArticleContent.objects.count() # Changed from Article
    ArticleGrouper.objects.count() # Added grouper count check, useful for health
    if not NewsBlogConfig.objects.count():
        raise RuntimeError('not NewsBlogConfig.objects.count()')
