from django.conf import settings
from django.urls.exceptions import NoReverseMatch

from aldryn_search.utils import get_index_base
from haystack.constants import DEFAULT_ALIAS

from .models import ArticleContent  # Changed Article


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
            # Path updated
            'article_grouper__app_config__search_indexed': True,
            'translations__language_code': language,
        }
        return kwargs

    def get_index_queryset(self, language):
        queryset = super().get_index_queryset(language)
        # Reindex when version states change. Custom Version signals should
        # trigger Haystack updates for published or unpublished articles.

        from django.contrib.contenttypes.models import ContentType
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version
        from django.utils import timezone  # For published__lte check
        # from django.utils.translation import get_language # If needed for language fallback

        content_type = ContentType.objects.get_for_model(self.get_model())

        # Get PKs of ArticleContent objects that have a currently published version
        published_content_pks = Version.objects.filter(
            content_type=content_type,
            state=PUBLISHED,
            # Ensure it's currently published (not scheduled for future)
            created__lte=timezone.now(),
        ).values_list('object_id', flat=True).distinct()

        queryset = self.get_model()._original_manager.filter(
            pk__in=published_content_pks,
        )  # Use _original_manager to bypass version filtering

        # If Haystack's multilingual processing isn't sufficient, or if using
        # Parler's translated() is preferred, the `language` parameter is passed
        # by Haystack when building for a specific language.
        if language:
            queryset = queryset.translated(language)  # Parler manager method
        return queryset

    def get_model(self):
        return ArticleContent  # Changed from Article

    def prepare(self, obj):
        data = super().prepare(obj)
        data['language'] = self.get_language(obj)
        data['url'] = self.get_url(obj)
        return data

    def get_search_data(self, article_content, language, request):  # Renamed obj to article_content
        # article_content is ArticleContent
        if article_content.search_data:
            return article_content.search_data
        return article_content.get_search_data(language=language, request=request)

    def should_update(self, instance, **kwargs):
        # instance is ArticleContent
        using = getattr(self, '_backend_alias', DEFAULT_ALIAS)
        language = self.get_current_language(using=using, obj=instance)
        return language in instance.get_available_languages()
