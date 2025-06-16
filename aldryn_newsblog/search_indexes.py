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
        # FIXME #VERSIONING: Haystack RealtimeSignalProcessor (if used) needs to be versioning-aware.
        # It should ideally update the index only when a Version is published, unpublished, or a
        # published version's content is deleted. This might require custom signal handlers
        # connected to djangocms_versioning's signals, or disabling Haystack's default
        # auto-update for ArticleContent and manually triggering reindex on versioning events.
        # The queryset below now filters for currently published content.

        from django.contrib.contenttypes.models import ContentType
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version
        from django.utils import timezone # For published__lte check
        # from django.utils.translation import get_language # If needed for language fallback

        content_type = ContentType.objects.get_for_model(self.get_model())

        # Get PKs of ArticleContent objects that have a currently published version
        published_content_pks = Version.objects.filter(
            content_type=content_type,
            state=PUBLISHED,
            published__lte=timezone.now() # Ensure it's currently published (not scheduled for future)
        ).values_list('object_id', flat=True).distinct()

        queryset = self.get_model()._base_manager.filter(pk__in=published_content_pks) # Use _base_manager to avoid default filtering

        # If Haystack's multilingual processing isn't sufficient, or if using Parler's translated() is preferred:
        # The `language` parameter is passed by Haystack when building for a specific language.
        if language:
             queryset = queryset.translated(language) # Assuming Parler's translated() manager method
        return queryset

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
