from django.urls import NoReverseMatch
from django.utils.translation import get_language_from_request
from django.utils.translation import gettext_lazy as _

from cms.apphook_pool import apphook_pool
from cms.menu_bases import CMSAttachMenu
from menus.base import NavigationNode
from menus.menu_pool import menu_pool

from aldryn_newsblog.compat import toolbar_edit_mode_active

from .models import ArticleContent


class NewsBlogMenu(CMSAttachMenu):
    name = _('Aldryn NewsBlog Menu')

    def get_queryset(self, request):
        """Returns base queryset with support for preview-mode."""
        queryset = ArticleContent.objects
        if not (request.toolbar and toolbar_edit_mode_active(request)):
            from django.contrib.contenttypes.models import ContentType
            from djangocms_versioning.models import Version
            from djangocms_versioning.constants import PUBLISHED
            from django.utils import timezone
            from django.db.models import Subquery

            content_type = ContentType.objects.get_for_model(ArticleContent)
            published_pks = Version.objects.filter(
                content_type=content_type,
                state=PUBLISHED,
                created__lte=timezone.now(),
            ).values_list('object_id', flat=True).distinct()
            queryset = queryset.filter(pk__in=Subquery(published_pks))
        return queryset

    def get_nodes(self, request):
        nodes = []
        language = get_language_from_request(request, check_path=True)
        articles = self.get_queryset(request).active_translations(language)

        if hasattr(self, 'instance') and self.instance:
            app = apphook_pool.get_apphook(self.instance.application_urls)
            if app:
                try:
                    config = app.get_config(self.instance.application_namespace)
                    if config:
                        articles = articles.filter(app_config=config)
                except NotImplementedError:
                    pass  # Configurable AppHooks must implement this method

        for article in articles:
            try:
                url = article.get_absolute_url(language=language)
            except NoReverseMatch:
                url = None

            if url:
                node = NavigationNode(article.safe_translation_getter(
                    'title', language_code=language), url, article.pk)
                nodes.append(node)
        return nodes


menu_pool.register_menu(NewsBlogMenu)
