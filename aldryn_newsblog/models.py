import django.core.validators
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.timezone import now
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from cms.models.fields import PlaceholderField
from cms.models.pluginmodel import CMSPlugin
from cms.utils.i18n import get_current_language, get_redirect_on_fallback

from aldryn_apphooks_config.fields import AppHookConfigField
from aldryn_categories.fields import CategoryManyToManyField
from aldryn_categories.models import Category
from aldryn_people.models import Person
from aldryn_translation_tools.models import (
    TranslatedAutoSlugifyMixin, TranslationHelperMixin,
)
from djangocms_text.fields import HTMLField
from filer.fields.image import FilerImageField
from parler.models import TranslatableModel, TranslatedFields
from sortedm2m.fields import SortedManyToManyField
from taggit.managers import TaggableManager
from taggit.models import Tag

from aldryn_newsblog.compat import toolbar_edit_mode_active
from aldryn_newsblog.utils.utilities import get_valid_languages_from_request

from .cms_appconfig import NewsBlogConfig
from .managers import RelatedManager
from .utils import get_plugin_index_data, get_request, strip_tags


if settings.LANGUAGES:
    LANGUAGE_CODES = [language[0] for language in settings.LANGUAGES]
elif settings.LANGUAGE:
    LANGUAGE_CODES = [settings.LANGUAGE]
else:
    raise ImproperlyConfigured(
        'Neither LANGUAGES nor LANGUAGE was found in settings.')


# At startup time, SQL_NOW_FUNC will contain the database-appropriate SQL to
# obtain the CURRENT_TIMESTAMP.
SQL_NOW_FUNC = {
    'mssql': 'GetDate()', 'mysql': 'NOW()', 'postgresql': 'now()',
    'sqlite': 'CURRENT_TIMESTAMP', 'oracle': 'CURRENT_TIMESTAMP'
}[connection.vendor]

SQL_IS_TRUE = {
    'mssql': '== TRUE', 'mysql': '= 1', 'postgresql': 'IS TRUE',
    'sqlite': '== 1', 'oracle': 'IS TRUE'
}[connection.vendor]


class Serial(models.Model):
    """Article as a serial."""

    name = models.CharField(_('Name'), max_length=255)

    def __str__(self):
        return self.name


class ArticleGrouper(models.Model):
    app_config = AppHookConfigField(
        NewsBlogConfig,
        verbose_name=_('Section'),
        help_text='',
        on_delete=models.CASCADE,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('owner'),
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        Person,
        null=True,
        blank=True,
        verbose_name=_('author'),
        on_delete=models.SET_NULL,
    )
    serial = models.ForeignKey(
        Serial,
        verbose_name=_('Serial'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    episode = models.PositiveIntegerField(verbose_name=_('Episode'), default=1)
    # objects = RelatedManager() # Commented out for now

    def __str__(self):
        return f"ArticleGrouper {self.pk}"


class ArticleContent(TranslatedAutoSlugifyMixin,
                     TranslationHelperMixin,
                     TranslatableModel):

    # TranslatedAutoSlugifyMixin options
    slug_source_field_name = 'title'
    slug_default = _('untitled-article')
    # when True, updates the article's search_data field
    # whenever the article is saved or a plugin is saved
    # on the article's content placeholder.
    update_search_on_save = getattr(
        settings,
        'ALDRYN_NEWSBLOG_UPDATE_SEARCH_DATA_ON_SAVE',
        False
    )

    article_grouper = models.ForeignKey(
        ArticleGrouper,
        on_delete=models.CASCADE,
        related_name='contents'
    )

    translations = TranslatedFields(
        title=models.CharField(_('title'), max_length=234),
        slug=models.SlugField(
            verbose_name=_('slug'),
            max_length=255,
            db_index=True,
            blank=True,
            help_text=_(
                'Used in the URL. If changed, the URL will change. '
                'Clear it to have it re-created automatically.'),
            unique=False, # Unique per language AND grouper is handled by meta
        ),
        lead_in=HTMLField(
            verbose_name=_('lead'), default='',
            help_text=_(
                'The lead gives the reader the main idea of the story, this '
                'is useful in overviews, lists or as an introduction to your '
                'article.'
            ),
            blank=True,
        ),
        meta_title=models.CharField(
            max_length=255, verbose_name=_('meta title'),
            blank=True, default=''),
        meta_description=models.TextField(
            verbose_name=_('meta description'), blank=True, default=''),
        meta_keywords=models.TextField(
            verbose_name=_('meta keywords'), blank=True, default=''),
        meta={'unique_together': (('language_code', 'master', 'slug'),)},

        search_data=models.TextField(blank=True, editable=False)
    )

    content = PlaceholderField('newsblog_article_content',
                               related_name='newsblog_article_content')
    # author, owner, app_config moved to ArticleGrouper
    categories = CategoryManyToManyField('aldryn_categories.Category',
                                         verbose_name=_('categories'),
                                         blank=True)
    # publishing_date, is_published removed for versioning
    is_featured = models.BooleanField(_('is featured'), default=False,
                                      db_index=True)
    featured_image = FilerImageField(
        verbose_name=_('featured image'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    tags = TaggableManager(blank=True)

    # Setting "symmetrical" to False since it's a bit unexpected that if you
    # set "B relates to A" you immediately have also "A relates to B". It have
    # to be forced to False because by default it's True if rel.to is "self":
    #
    # https://github.com/django/django/blob/1.8.4/django/db/models/fields/related.py#L2144
    #
    # which in the end causes to add reversed releted-to entry as well:
    #
    # https://github.com/django/django/blob/1.8.4/django/db/models/fields/related.py#L977
    related = SortedManyToManyField(
        ArticleGrouper,  # Changed from 'self'
        verbose_name=_('related articles'),
        blank=True,
        symmetrical=False
    )
    # serial, episode moved to ArticleGrouper

    # objects = RelatedManager() # Commented out, to be reviewed

    class Meta:
        # Publishing date is no longer on this model. Versioning will handle published state.
        # Ordering might be by grouper's creation date or ID, or by version's publish date.
        # For now, let's use grouper's PK.
        ordering = ['-article_grouper__pk'] # Placeholder ordering
        # unique_together = (('article_grouper', 'slug'),) # Removed due to system check errors

    # Removed published and future properties as they depended on fields now removed.

    def get_absolute_url(self, language=None):
        """Returns the url for this ArticleContent in the selected permalink format."""
        if not language:
            language = get_current_language()
        kwargs = {}
        # app_config is now on the grouper
        permalink_type = self.article_grouper.app_config.permalink_type

        from djangocms_versioning.models import Version
        from djangocms_versioning.constants import PUBLISHED
        # django.urls.NoReverseMatch is already imported for some cases
        # django.utils.translation.override, get_current_language are already imported
        # django.urls.reverse is already imported

        if not language:
            language = get_current_language() # Ensure language is set first

        publishing_date_for_url = None
        try:
            # Get current version for this content object
            # Use versioning_api.get_version(self) for robustness if available, else direct Version query.
            # For now, assuming Version.objects.get_for_content(self) is appropriate to get the
            # version record that corresponds to this specific ArticleContent instance.
            version = Version.objects.get_for_content(self)
            if version.state == PUBLISHED and version.published:
                publishing_date_for_url = version.published.date()
            else:
                # Not a published version, or no specific publish date on the version record.
                # No canonical public URL for non-published content.
                return None
        except Version.DoesNotExist:
            # No version object at all for this content. Cannot determine published state or date.
            return None

        if publishing_date_for_url is None: # Should be caught by above, but as a safeguard
            return None

        # Current permalink_type and kwargs logic based on publishing_date can remain,
        # as it's now only reached if publishing_date_for_url is valid from a published version.
        kwargs = {}
        permalink_type = self.article_grouper.app_config.permalink_type

        if 'y' in permalink_type:
            kwargs.update(year=publishing_date_for_url.year)
        if 'm' in permalink_type:
            kwargs.update(month="%02d" % publishing_date_for_url.month)
        if 'd' in permalink_type:
            kwargs.update(day="%02d" % publishing_date_for_url.day)

        # Slug and PK handling
        # The permalink structure might use the content's PK or the grouper's PK.
        # Original urls.py patterns use slug or pk (which usually means content's pk for DetailView).
        # If 'i' (ID) is in permalink, it typically refers to the object 'self'.
        if 'i' in permalink_type:
            kwargs.update(pk=self.pk)

        if 's' in permalink_type:
            slug_val, lang_val = self.known_translation_getter(
                'slug', default=None, language_code=language
            )
            if slug_val is None: # If slug is None for the current language, cannot form URL
                return None
            # The original logic for redirect_on_fallback and changing language variable here
            # can be complex and might interact with how Parler/CMS handle language in URLs.
            # For now, just use the slug for the requested language.
            kwargs.update(slug=slug_val)

        if not kwargs: # If no kwargs were populated (e.g. permalink_type was empty or only 's' but no slug)
            return None # Cannot form a URL

        if self.article_grouper.app_config and self.article_grouper.app_config.namespace:
            namespace_str = f'{self.article_grouper.app_config.namespace}:'
        else:
            namespace_str = ''

        try:
            with override(language): # Ensure correct language context for reverse
                url = reverse(f'{namespace_str}article-detail', kwargs=kwargs)
        except NoReverseMatch:
            return None # If URL cannot be reversed (e.g. bad slug, or no pattern matches for kwargs)

        return url

    def get_search_data(self, language=None, request=None):
        """
        Provides an index for use with Haystack, or, for populating
        ArticleContent.translations.search_data.
        """
        if not self.pk:
            return ''
        if language is None:
            language = get_current_language()
        if request is None:
            request = get_request(language=language)
        description = self.safe_translation_getter('lead_in', '')
        text_bits = [strip_tags(description)]
        for category in self.categories.all():
            text_bits.append(
                force_str(category.safe_translation_getter('name')))
        for tag in self.tags.all():
            text_bits.append(force_str(tag.name))
        if self.content:
            plugins = self.content.cmsplugin_set.filter(language=language)
            for base_plugin in plugins:
                plugin_text_content = ' '.join(
                    get_plugin_index_data(base_plugin, request))
                text_bits.append(plugin_text_content)
        return ' '.join(text_bits)

    def save(self, *args, **kwargs):
        # Update the search index
        if self.update_search_on_save:
            # Ensure to pass the current language to get_search_data
            current_language = self.get_current_language() if hasattr(self, 'get_current_language') else get_current_language()
            self.search_data = self.get_search_data(language=current_language)

        # Author creation logic is removed from here.
        # It should be handled when an ArticleGrouper instance is created.

        # slug would be generated by TranslatedAutoSlugifyMixin
        super().save(*args, **kwargs)

    def __str__(self):
        return self.safe_translation_getter('title', any_language=True)


class PluginEditModeMixin:
    def get_edit_mode(self, request):
        """
        Returns True only if an operator is logged-into the CMS and is in
        edit mode.
        """
        return (
            hasattr(request, 'toolbar') and request.toolbar and  # noqa: W504
            toolbar_edit_mode_active(request)
        )


class AdjustableCacheModelMixin(models.Model):
    # NOTE: This field shouldn't even be displayed in the plugin's change form
    # if using django CMS < 3.3.0
    cache_duration = models.PositiveSmallIntegerField(
        default=0,  # not the most sensible, but consistent with older versions
        blank=False,
        help_text=_(
            "The maximum duration (in seconds) that this plugin's content "
            "should be cached.")
    )

    class Meta:
        abstract = True


class NewsBlogCMSPlugin(CMSPlugin):
    """AppHookConfig aware abstract CMSPlugin class for Aldryn Newsblog"""
    # avoid reverse relation name clashes by not adding a related_name
    # to the parent plugin
    cmsplugin_ptr = models.OneToOneField(
        CMSPlugin,
        related_name='+',
        parent_link=True,
        on_delete=models.CASCADE,
    )

    app_config = models.ForeignKey(
        NewsBlogConfig,
        verbose_name=_('Apphook configuration'),
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True

    def copy_relations(self, old_instance):
        self.app_config = old_instance.app_config


class NewsBlogArchivePlugin(PluginEditModeMixin, AdjustableCacheModelMixin,
                            NewsBlogCMSPlugin):
    # NOTE: the PluginEditModeMixin is eventually used in the cmsplugin, not
    # here in the model.
    def __str__(self):
        return gettext('%s archive') % (self.app_config.get_app_title(), )


class NewsBlogArticleSearchPlugin(NewsBlogCMSPlugin):
    max_articles = models.PositiveIntegerField(
        _('max articles'), default=10,
        validators=[django.core.validators.MinValueValidator(1)],
        help_text=_('The maximum number of found articles display.')
    )

    def __str__(self):
        return gettext('%s search') % (self.app_config.get_app_title(), )


class NewsBlogAuthorsPlugin(PluginEditModeMixin, NewsBlogCMSPlugin):
    def get_authors(self, request):
        """
        Returns a queryset of authors (people who have published an article),
        annotated by the number of articles (article_count) that are visible to
        the current user. If this user is anonymous, then this will be all
        articles that are published and whose publishing_date has passed. If the
        user is a logged-in cms operator, then it will be all articles.
        """

        # The basic subquery (for logged-in content managers in edit mode)
        from django.db.models import Count, Q
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version

        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        edit_mode = self.get_edit_mode(request)

        # Get all Person objects who are authors of at least one ArticleGrouper in this app_config
        authors_qs = Person.objects.filter(
            articlegrouper__app_config=self.app_config
        ).distinct()

        annotated_authors = []
        for author in authors_qs:
            # For each author, count their published ArticleContent versions within this app_config.
            # A content is considered published if it has a Version in PUBLISHED state.

            # Subquery to find PKs of ArticleContent by this author in this app_config
            content_pks_by_author_for_appconfig = ArticleContent.objects.filter(
                article_grouper__author=author,
                article_grouper__app_config=self.app_config
            ).values_list('pk', flat=True)

            if edit_mode:
                # In edit mode, count could include all versions or be based on some other logic.
                # For simplicity and consistency with original intent of showing published counts,
                # let's stick to published counts even in edit mode for now, unless requirements differ.
                # Or, count all content if that's the desired edit-mode behavior.
                # The original raw SQL didn't significantly change query for edit mode beyond base subquery.
                # Let's count published versions for now.
                count = Version.objects.filter(
                    content_type=content_type_ac,
                    object_id__in=content_pks_by_author_for_appconfig,
                    state=PUBLISHED
                ).count()
            else: # Not in edit mode, only count PUBLISHED versions
                count = Version.objects.filter(
                    content_type=content_type_ac,
                    object_id__in=content_pks_by_author_for_appconfig,
                    state=PUBLISHED
                ).count()

            if count > 0:
                author.article_count = count  # Annotate instance
                annotated_authors.append(author)

        return sorted(annotated_authors, key=lambda x: x.article_count, reverse=True)

    def __str__(self):
        return gettext('%s authors') % (self.app_config.get_app_title(), )


class NewsBlogCategoriesPlugin(PluginEditModeMixin, NewsBlogCMSPlugin):
    def __str__(self):
        return gettext('%s categories') % (self.app_config.get_app_title(), )

    def get_categories(self, request):
        """
        Returns a list of categories, annotated by the number of articles
        (article_count) that are visible to the current user. If this user is
        anonymous, then this will be all articles that are published and whose
        publishing_date has passed. If the user is a logged-in cms operator,
        then it will be all articles.
        """

        from django.db.models import Count, Q
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version

        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        edit_mode = self.get_edit_mode(request)

        # Get all Categories that are used by ArticleContent in this app_config
        categories_qs = Category.objects.filter(
            articlecontent__article_grouper__app_config=self.app_config
        ).distinct()

        annotated_categories = []
        for category in categories_qs:
            # For each category, count its published ArticleContent versions within this app_config.
            content_pks_in_category_for_appconfig = ArticleContent.objects.filter(
                categories=category,
                article_grouper__app_config=self.app_config
            ).values_list('pk', flat=True)

            if edit_mode:
                # Similar to get_authors, sticking to published counts for now.
                count = Version.objects.filter(
                    content_type=content_type_ac,
                    object_id__in=content_pks_in_category_for_appconfig,
                    state=PUBLISHED
                ).count()
            else: # Not in edit mode
                count = Version.objects.filter(
                    content_type=content_type_ac,
                    object_id__in=content_pks_in_category_for_appconfig,
                    state=PUBLISHED
                ).count()

            if count > 0:
                category.article_count = count # Annotate instance
                annotated_categories.append(category)

        return sorted(annotated_categories, key=lambda x: x.article_count, reverse=True)


class NewsBlogFeaturedArticlesPlugin(PluginEditModeMixin, NewsBlogCMSPlugin):
    article_count = models.PositiveIntegerField(
        default=1,
        validators=[django.core.validators.MinValueValidator(1)],
        help_text=_('The maximum number of featured articles display.')
    )

    def get_articles(self, request):
        # FIXME: This logic needs review with versioning to correctly filter by published state.
        if not self.article_count:
            return ArticleContent.objects.none()

        # Base queryset for ArticleContent linked to the correct app_config and featured
        queryset = ArticleContent.objects.filter(
            article_grouper__app_config=self.app_config,
            is_featured=True
        )

        languages = get_valid_languages_from_request(
            self.app_config.namespace, request)
        if self.language not in languages:
            return queryset.none() # Return empty from the current queryset

        queryset = queryset.translated(*languages)

        # Placeholder: Actual published state filtering would involve djangocms-versioning's Version model.
        # Example:
        # if not self.get_edit_mode(request):
        #     ct = ContentType.objects.get_for_model(ArticleContent)
        #     published_pks = Version.objects.filter(
        #         content_type=ct, object_id__in=queryset.values('pk'), state=PUBLISHED
        #     ).values_list('object_id', flat=True)
        #     queryset = queryset.filter(pk__in=published_pks)
        # else: # In edit mode, maybe order differently or show all versions' contents
        #     pass

        # For now, returning without explicit published filter beyond what was in ArticleContent
        return queryset[:self.article_count]

    def __str__(self):
        if not self.pk:
            return 'featured articles'
        prefix = self.app_config.get_app_title()
        if self.article_count == 1:
            title = gettext('featured article')
        else:
            title = gettext('featured articles: %(count)s') % {
                'count': self.article_count,
            }
        return f'{prefix} {title}'


class NewsBlogLatestArticlesPlugin(PluginEditModeMixin,
                                   AdjustableCacheModelMixin,
                                   NewsBlogCMSPlugin):
    latest_articles = models.IntegerField(
        default=5,
        help_text=_('The maximum number of latest articles to display.')
    )
    exclude_featured = models.PositiveSmallIntegerField(
        default=0,
        blank=True,
        help_text=_(
            'The maximum number of featured articles to exclude from display. '
            'E.g. for uses in combination with featured articles plugin.')
    )

    def get_articles(self, request):
        """
        Returns a queryset of the latest N articles. N is the plugin setting:
        latest_articles.
        """
        # FIXME: This logic needs review with versioning for published state and ordering.
        languages = get_valid_languages_from_request(
            self.app_config.namespace, request)
        if self.language not in languages:
            return ArticleContent.objects.none()

        base_queryset = ArticleContent.objects.filter(
            article_grouper__app_config=self.app_config
        ).translated(*languages)

        excluded_pks = []
        if self.exclude_featured > 0:
            # This part also needs to consider published versions of featured articles
            featured_qs = base_queryset.filter(is_featured=True)
            # Placeholder for versioning-aware ordering and filtering for featured
            # featured_qs = filter_by_published_versions(featured_qs, request)
            excluded_pks = featured_qs.values_list('pk', flat=True)[:self.exclude_featured]

        queryset = base_queryset.exclude(pk__in=excluded_pks)

        # Placeholder: Actual published state filtering and ordering would involve djangocms-versioning.
        # Example:
        # if not self.get_edit_mode(request):
        #     ct = ContentType.objects.get_for_model(ArticleContent)
        #     published_pks = Version.objects.filter(
        #         content_type=ct, object_id__in=queryset.values('pk'), state=PUBLISHED
        #     ).order_by('-published_date').values_list('object_id', flat=True) # Assuming published_date on Version
        #     queryset = queryset.filter(pk__in=published_pks) # This re-filters, better to order then slice
        #     # A more complex query would be needed to order by version's publishing date correctly before slicing
        # else: # In edit mode
        #     queryset = queryset.order_by('-article_grouper__pk') # Fallback ordering for now

        return queryset[:self.latest_articles]

    def __str__(self):
        return gettext('%(app_title)s latest articles: %(latest_articles)s') % {
            'app_title': self.app_config.get_app_title(),
            'latest_articles': self.latest_articles,
        }


class NewsBlogRelatedPlugin(PluginEditModeMixin, AdjustableCacheModelMixin,
                            CMSPlugin):
    # NOTE: This one does NOT subclass NewsBlogCMSPlugin. This is because this
    # plugin can really only be placed on the article detail view in an apphook.
    cmsplugin_ptr = models.OneToOneField(
        CMSPlugin,
        related_name='+',
        parent_link=True,
        on_delete=models.CASCADE,
    )

    def get_articles(self, article, request):
        """
        Returns a queryset of articles that are related to the given article.
        """
        # FIXME: This logic needs review with versioning. `article` is ArticleContent.
        # `article.related` points to ArticleGrouper instances.
        if not article or not hasattr(article, 'article_grouper'):
            return ArticleContent.objects.none()

        languages = get_valid_languages_from_request(
            article.article_grouper.app_config.namespace, request)
        if self.language not in languages:
            return ArticleContent.objects.none()

        related_groupers = article.related.all() # QuerySet of ArticleGrouper

        # Placeholder: Fetch published ArticleContent versions for these groupers.
        # This is a conceptual query.
        # queryset = ArticleContent.objects.filter(
        #     article_grouper__in=related_groupers
        # ).translated(*languages)
        # if not self.get_edit_mode(request):
        #     ct = ContentType.objects.get_for_model(ArticleContent)
        #     published_pks = Version.objects.filter(
        #         content_type=ct, object_id__in=queryset.values('pk'), state=PUBLISHED
        #     ).values_list('object_id', flat=True)
        #     queryset = queryset.filter(pk__in=published_pks)
        # return queryset
        # For now, returning all contents of related groupers, not filtered by publish state
        return ArticleContent.objects.filter(article_grouper__in=related_groupers).translated(*languages)

    def __str__(self):
        return gettext('Related articles')


class NewsBlogTagsPlugin(PluginEditModeMixin, NewsBlogCMSPlugin):

    def get_tags(self, request):
        """
        Returns a queryset of tags, annotated by the number of articles
        (article_count) that are visible to the current user. If this user is
        anonymous, then this will be all articles that are published and whose
        publishing_date has passed. If the user is a logged-in cms operator,
        then it will be all articles.
        """
        # Attempting ORM-based logic for versioning:
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Count, Subquery, OuterRef
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version
        from taggit.models import Tag, TaggedItem
        from django.utils import timezone

        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        # edit_mode = self.get_edit_mode(request) # Not used in this version of the query

        # 1. Get PKs of ArticleContent that are published AND belong to this plugin's app_config.
        # This subquery will find all object_ids (ArticleContent pks) that meet the criteria.
        published_content_in_appconfig_pks = Subquery(
            Version.objects.filter(
                content_type=content_type_ac,
                state=PUBLISHED,
                published__lte=timezone.now()
            ).filter(
                object_id__in=ArticleContent.objects.filter(
                    article_grouper__app_config=self.app_config
                ).values('pk')
            ).values_list('object_id', flat=True).distinct()
        )

        # 2. Filter TaggedItem objects:
        #    - content_type must be ArticleContent.
        #    - object_id must be in our list of published_content_in_appconfig_pks.
        relevant_tagged_item_pks = TaggedItem.objects.filter(
            content_type=content_type_ac,
            object_id__in=published_content_in_appconfig_pks
        ).values_list('pk', flat=True)

        # 3. Annotate Tags with counts of these relevant_tagged_items.
        # We only want tags that are associated with at least one of these relevant items.
        tags_with_counts = Tag.objects.filter(
            taggeditem_items__pk__in=relevant_tagged_item_pks # Filter tags that are part of relevant items
        ).annotate(
            num_articles=Count('taggeditem_items', filter=Q(taggeditem_items__pk__in=relevant_tagged_item_pks))
            # Count only the tagged items that are relevant (published, correct app_config, etc.)
        ).filter(num_articles__gt=0).order_by('-num_articles', 'name') # Filter out tags with no articles after versioning filter

        # The above annotation should correctly count only the pre-filtered relevant_tagged_item_pks.
        # If performance is an issue or it's incorrect, the python loop below is a fallback.
        # For now, let's trust the annotation if possible.

        # Fallback Python-side counting (if complex annotation fails or is too slow):
        # relevant_tags_qs = Tag.objects.filter(pk__in=relevant_tagged_item_pks.values_list('tag_id', flat=True).distinct())
        # final_tags_with_counts = []
        # for tag in relevant_tags_qs:
        #     count = TaggedItem.objects.filter(
        #         pk__in=relevant_tagged_item_pks, # Count only from our pre-filtered set of items
        #         tag=tag
        #     ).count()
        #     if count > 0:
        #         tag.num_articles = count
        #         final_tags_with_counts.append(tag)
        # return sorted(final_tags_with_counts, key=lambda t: (-t.num_articles, t.name))

        return list(tags_with_counts)

    def __str__(self):
        return gettext('%s tags') % (self.app_config.get_app_title(), )


@receiver(post_save, dispatch_uid='article_update_search_data')
def update_search_data(sender, instance, **kwargs):
    """
    Upon detecting changes in a plugin used in an Article's content
    (PlaceholderField), update the article's search_index so that we can
    perform simple searches even without Haystack, etc.
    """
    is_cms_plugin = issubclass(instance.__class__, CMSPlugin)

    if ArticleContent.update_search_on_save and is_cms_plugin: # Changed Article to ArticleContent
        placeholder = (getattr(instance, '_placeholder_cache', None) or  # noqa: W504
                       instance.placeholder)
        if hasattr(placeholder, '_attached_model_cache'):
            if placeholder._attached_model_cache == ArticleContent: # Changed Article to ArticleContent
                try:
                    # Ensure placeholder.pk is valid if placeholder comes from a just deleted plugin
                    if placeholder and placeholder.pk:
                        article_content = placeholder._attached_model_cache.objects.language( # Renamed variable
                            instance.language).get(content=placeholder.pk)
                        current_language = instance.language or get_current_language()
                        # Pass request if available, needed by get_plugin_index_data
                        # This might be problematic if request is not easily available here.
                        # Consider if get_search_data truly needs request or can work without it.
                        article_content.search_data = article_content.get_search_data(current_language, request=get_request())
                        article_content.save()
                except ArticleContent.DoesNotExist:
                    pass # ArticleContent might have been deleted


# Full implementation of the article_content_copy function
from parler.utils.context import switch_language
from cms.api import add_plugin

def article_content_copy(original_content, user=None):
    """
    Copies an ArticleContent instance, including its translations,
    m2m relations, and placeholder content.
    """
    # 1. Create New Instance (Shell) + Copy Direct Non-Relational Fields
    direct_fields = {}
    if hasattr(original_content, 'is_featured'):
        direct_fields['is_featured'] = original_content.is_featured
    # Add any other direct, non-translated, non-relational fields from ArticleContent here

    # Use _original_manager to avoid creating a Version record prematurely by djangocms-versioning
    new_content = ArticleContent._original_manager.create(
        article_grouper=original_content.article_grouper,
        **direct_fields
    )

    # 2. Copy Translated Fields
    for language_code in original_content.get_available_languages():
        with switch_language(new_content, language_code):
            original_translation = original_content.safe_get_translation(language_code, any_language=False)
            if original_translation:
                new_content.title = original_translation.title
                # Slug is regenerated by TranslatedAutoSlugifyMixin if set to None or if it conflicts.
                # If exact copy is needed and might conflict, this needs more sophisticated handling.
                new_content.slug = None # Let it regenerate to avoid immediate unique constraint issues
                new_content.lead_in = original_translation.lead_in
                new_content.meta_title = original_translation.meta_title
                new_content.meta_description = original_translation.meta_description
                new_content.meta_keywords = original_translation.meta_keywords
                # search_data is auto-generated on save by get_search_data() if update_search_on_save is True
            new_content.save() # This save will also trigger TranslatedAutoSlugifyMixin for slug

    # 3. Copy featured_image (FilerImageField - ForeignKey)
    if original_content.featured_image:
        new_content.featured_image = original_content.featured_image
        # Save this specific field update if not covered by earlier saves
        # However, parler's save() on translation might not save main model fields.
        # So, an explicit save on the main model for FKs is safer.
        new_content.save(update_fields=['featured_image'])


    # 4. Copy ManyToMany Relationships (after new_content has a PK)
    new_content.categories.set(original_content.categories.all())
    new_content.tags.set(original_content.tags.all())
    new_content.related.set(original_content.related.all()) # related points to ArticleGrouper

    # 5. Copy PlaceholderField ('content')
    # FIXME #VERSIONING: Placeholder content copying.
    # The current logic iterates through top-level plugins in the original placeholder
    # and uses `cms.api.add_plugin` to add them to the new placeholder. This relies on:
    # 1. Each plugin type correctly implementing its `copy_relations` method if it has
    #    custom data or child plugins that need deep copying (e.g., by handling the `source_plugin`
    #    argument passed to `copy_relations` by `cms.api.add_plugin` when `target_placeholder` is specified).
    # 2. `add_plugin` sufficiently handling the recreation for standard cases by passing attributes.
    # Limitations:
    # - Deeply nested plugins: `add_plugin` itself does not recursively copy child plugins.
    #   If a plugin has children, its `copy_relations` method (or equivalent logic if not using `copy_relations` directly)
    #   must handle copying its children. Standard CMS plugins usually do this. Custom or third-party plugins might not.
    # - Custom plugin data: If a plugin stores data in related models not automatically
    #   handled by a simple field copy or its `copy_relations`, that data won't be copied.
    # - Plugin instance fields vs. attributes: Ensure all relevant data is passed via
    #   `**plugin_base.attributes` or copied manually if stored as direct fields on the
    #   plugin model instance and not handled by `copy_relations`. The `attributes` dictionary
    #   should contain all serializable fields of the plugin instance.
    # For a more universally robust solution, especially with diverse or complex third-party plugins,
    # `cms.api.copy_plugins_to_placeholder(original_placeholder, new_placeholder)` could be considered,
    # as it's designed for deep, faithful copies of entire placeholder contents, including structure.
    # However, this requires ensuring that all plugins involved are compatible with this API.
    # The current approach is a common pattern for basic placeholder copying.
    original_placeholder = original_content.content
    new_placeholder = new_content.content # Accessing it should ensure it exists or is created

    if original_placeholder and new_placeholder:
        # It's generally safer to clear the new placeholder if it might have default plugins,
        # though for a fresh instance via _original_manager.create(), it should be empty.
        new_placeholder.clear()
        plugins = original_placeholder.get_plugins_list() # Gets only top-level plugins
        for plugin_base in plugins:
            # Create a new plugin instance by copying from the original.
            # The `add_plugin` API will call the plugin's `copy_relations` method
            # if `source_plugin` is provided, which can handle child plugins and other relations.
            # However, we are iterating only top-level plugins here.
            # A more robust copy would use cms.api.copy_plugins_to_placeholder.
            # For now, this copies top-level plugins and their direct data.
            add_plugin(
                placeholder=new_placeholder,
                plugin_type=plugin_base.plugin_type,
                language=plugin_base.language,
                # Pass attributes from original plugin. Ensure all necessary fields are included.
                # This relies on plugin_base.attributes being comprehensive.
                **plugin_base.attributes
            )
            # The previous FIXME about recursive copy is now part of the main comment above.
    else:
        if not original_placeholder:
            print(f"Warning: Original content {original_content.pk} has no placeholder 'content'.")
        if not new_placeholder:
            print(f"Warning: New content {new_content.pk} could not get/create placeholder 'content'.")

    return new_content
