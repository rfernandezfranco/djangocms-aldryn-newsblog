from django.conf import settings
from django.urls.exceptions import NoReverseMatch

from aldryn_search.utils import get_index_base
from haystack.constants import DEFAULT_ALIAS

from .models import ArticleContent # Changed Article


class ArticleIndex(get_index_base()):
    haystack_use_for_indexing = getattr(
        settings, 'ALDRYN_NEWSBLOG_SEARCH', True)

    index_title = True

    def get_language(self, obj):
        return getattr(obj, '_current_language', None)

    def get_title(self, obj):
        # obj is ArticleContent
        return obj.title

    def get_url(self, obj):
        # obj is ArticleContent
        using = getattr(self, '_backend_alias', DEFAULT_ALIAS)
        language = self.get_current_language(using=using, obj=obj)
        try:
            return obj.get_absolute_url(language)
        except NoReverseMatch:  # This occurs when Aldryn News Section is not published on the site.
            return None

    def get_description(self, obj):
        # obj is ArticleContent
        return obj.lead_in

    def get_index_kwargs(self, language):
        """
        This is called to filter the index queryset.
        app_config is on ArticleGrouper.
        """
        kwargs = {
            'article_grouper__app_config__search_indexed': True, # Path updated
            'translations__language_code': language,
        }
        return kwargs

    def get_index_queryset(self, language):
        queryset = super().get_index_queryset(language)
        # FIXME #VERSIONING: .published() manager method needs re-evaluation for versioning.
        # For now, just filter by language.
        return queryset.language(language) # Removed .published()

    def get_model(self):
        return ArticleContent # Changed from Article

    def get_search_data(self, article_content, language, request): # Renamed obj to article_content
        # article_content is ArticleContent
        return article_content.search_data

    def should_update(self, instance, **kwargs):
        # instance is ArticleContent
        using = getattr(self, '_backend_alias', DEFAULT_ALIAS)
        language = self.get_current_language(using=using, obj=instance)
        translations = instance.get_available_languages()
        return translations.filter(language_code=language).exists()
