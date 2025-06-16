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
        # FIXME #VERSIONING: Haystack's RealtimeSignalProcessor (if used for ArticleContent)
        # will not inherently understand the djangocms-versioning lifecycle. Saving an
        # ArticleContent draft would trigger reindexing of that draft's content (if not filtered out by
        # `should_update` or `index_queryset`), while publishing/unpublishing events
        # (which change the Version state and what `index_queryset` returns) might not trigger
        # the correct add/remove operations in the index for the specific content version.
        # Ideal Solution:
        # 1. Consider disabling Haystack's automatic RealtimeSignalProcessor for the ArticleContent model
        #    if it causes incorrect indexing during draft saves.
        # 2. Implement custom signal handlers that listen to djangocms-versioning's
        #    signals (e.g., `version_published`, `version_unpublished`, `version_archived`, `version_deleted`).
        # 3. These handlers should then manually call Haystack's index update methods:
        #    - On `version_published`: `SearchIndex().update_object(version.content, using=using)`
        #    - On `version_unpublished` / `version_archived`: `SearchIndex().remove_object(version.content, using=using)`
        #    - On `version_deleted` (if the content object is deleted with the version): `SearchIndex().remove_object(version.content, using=using)`
        # This ensures the search index accurately reflects the versioned state of published content.
        # The `index_queryset` below now correctly filters for currently published content for manual indexing runs.

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
