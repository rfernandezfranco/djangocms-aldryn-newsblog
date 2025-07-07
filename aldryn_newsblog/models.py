import django.core.validators
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.signals import post_save
from django.dispatch import receiver
from djangocms_versioning.constants import PUBLISHED
from djangocms_versioning.models import Version as CMSVersion
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
import warnings

from cms.models.fields import PlaceholderField
from cms.models.pluginmodel import CMSPlugin
from cms.utils.i18n import get_current_language

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

from parler.utils.context import switch_language
from cms.api import copy_plugins_to_placeholder

from aldryn_newsblog.compat import toolbar_edit_mode_active
from aldryn_newsblog.utils.utilities import get_valid_languages_from_request

from .cms_appconfig import NewsBlogConfig
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
            unique=False,  # Unique per language AND grouper is handled by meta
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

    # Used by django CMS preview functionality. Having this attribute tells the
    # CMS that the model provides a template that can be rendered on the
    # frontend when previewing versions in the admin.
    supports_preview = True

    #: Template used when rendering an ArticleContent instance outside of the
    #: normal CMS page routing.  This mirrors the default detail view template.
    preview_template = 'aldryn_newsblog/article_detail.html'

    def get_template(self):
        """Return the template used to render this object in the CMS."""
        return self.preview_template

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

    def safe_get_translation(self, language_code, any_language=False):
        """Return the translated instance for ``language_code`` or ``None``.

        This helper mirrors the ``safe_translation_getter`` API but returns
        the full translation object instead of a single field value.  If the
        translation for ``language_code`` doesn't exist and ``any_language`` is
        True, the first available translation will be returned instead.
        """
        try:
            return self.get_translation(language_code)
        except self.translations.model.DoesNotExist:
            if any_language:
                for lang in self.get_available_languages():
                    try:
                        return self.get_translation(lang)
                    except self.translations.model.DoesNotExist:
                        continue
        return None

    def _get_slug_queryset(self, lookup_model=None):
        """Return a queryset for slug uniqueness checks."""
        language = self.get_current_language() or settings.LANGUAGE_CODE
        if lookup_model is None:
            lookup_model = self.__class__
        manager = getattr(lookup_model, '_original_manager', lookup_model.objects)
        qs = manager.language(language)
        if not self.slug_globally_unique and self.article_grouper_id:
            qs = qs.filter(
                translations__language_code=language,
                article_grouper_id=self.article_grouper_id,
            )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        return qs

    class Meta:
        # Publishing date is no longer on this model. Versioning will handle published state.
        # Ordering might be by grouper's creation date or ID, or by version's publish date.
        # For now, let's use grouper's PK.
        ordering = ['-article_grouper__pk']  # Placeholder ordering
        # unique_together = (('article_grouper', 'slug'),)  # Removed due to system check errors

    # Removed published and future properties as they depended on fields now removed.

    def get_absolute_url(self, language=None):
        """Returns the url for this ArticleContent in the selected permalink format."""
        if not language:
            language = get_current_language()
        kwargs = {}
        # app_config is now on the grouper
        permalink_type = self.article_grouper.app_config.permalink_type

        # Using top-level imports: CMSVersion, PUBLISHED
        # django.urls.NoReverseMatch is already imported for some cases
        # django.utils.translation.override, get_current_language are already imported
        # django.urls.reverse is already imported

        if not language:
            language = get_current_language()  # Ensure language is set first

        publishing_date_for_url = None
        try:
            # Get current version for this content object
            # Use versioning_api.get_version(self) for robustness if available, else direct CMSVersion query.
            # For now, assuming CMSVersion.objects.get_for_content(self) is appropriate to get the
            # version record that corresponds to this specific ArticleContent instance.
            version = CMSVersion.objects.get_for_content(self)
            if version.state == PUBLISHED:
                publishing_date_for_url = version.created.date()
            else:
                # No canonical public URL for non-published content.
                return None
        except CMSVersion.DoesNotExist:
            # No version object at all for this content. Cannot determine published state or date.
            return None

        if publishing_date_for_url is None:  # Should be caught by above, but as a safeguard
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
            if slug_val is None:  # If slug is None for the current language, cannot form URL
                return None
            # The original logic for redirect_on_fallback and changing language variable here
            # can be complex and might interact with how Parler/CMS handle language in URLs.
            # For now, just use the slug for the requested language.
            kwargs.update(slug=slug_val)

        if not kwargs:  # If no kwargs were populated (e.g. permalink_type was empty or only 's' but no slug)
            return None  # Cannot form a URL

        if self.article_grouper.app_config and self.article_grouper.app_config.namespace:
            namespace_str = f'{self.article_grouper.app_config.namespace}:'
        else:
            namespace_str = ''

        with override(language):  # Ensure correct language context for reverse
            url = reverse(f'{namespace_str}article-detail', kwargs=kwargs)

        return url

    def get_preview_url(self, language=None):
        """Return a URL that can be used to preview this ArticleContent."""
        return self.get_absolute_url(language=language)

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
            current_language = (
                self.get_current_language()
                if hasattr(self, "get_current_language")
                else get_current_language()
            )
            self.search_data = self.get_search_data(language=current_language)

        # Author creation logic is removed from here.
        # It should be handled when an ArticleGrouper instance is created.

        # slug would be generated by TranslatedAutoSlugifyMixin
        super().save(*args, **kwargs)

        if self.update_search_on_save and not self.safe_get_translation(current_language).search_data:
            # When creating a new article, the translation may not yet have a
            # search_data value. Compute it after the initial save to ensure the
            # field gets stored correctly.
            self.search_data = self.get_search_data(language=current_language)
            # Temporarily disable the automatic update to avoid recursion
            orig_flag = self.update_search_on_save
            self.update_search_on_save = False
            super().save()
            self.update_search_on_save = orig_flag

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
        # Using top-level imports: CMSVersion, PUBLISHED

        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        languages = get_valid_languages_from_request(
            self.app_config.namespace, request
        )

        # Subquery to get PKs of ArticleContent that are PUBLISHED and belong to this app_config
        # Note: Current logic counts published for both edit and non-edit mode.
        # If edit_mode requires counting *all* articles, this subquery would need adjustment for that mode.
        published_content_pks_subquery = Subquery(
            ArticleContent.objects.filter(
                article_grouper__app_config=self.app_config,
                versions__content_type=content_type_ac,
                versions__state=PUBLISHED
            ).values('pk')
        )

        authors_with_counts = (
            Person.objects.active_translations(languages[0])
            .filter(
                articlegrouper__app_config=self.app_config,
                articlegrouper__contents__pk__in=published_content_pks_subquery,
            )
            .annotate(
                article_count=Count(
                    'articlegrouper__contents',
                    filter=Q(articlegrouper__contents__pk__in=published_content_pks_subquery),
                )
            )
            .filter(article_count__gt=0)
            .order_by('-article_count', 'translations__name')
            .distinct()
        )
# 'name' is a field on the Person translation model.
# Ordering uses 'translations__name' so authors with the same article_count
# appear alphabetically in the current language.
        # For aldryn-people, Person itself is not translatable by default, but has name fields.

        return list(authors_with_counts)

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
        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        languages = get_valid_languages_from_request(
            self.app_config.namespace, request)

        published_content_pks_subquery = Subquery(
            ArticleContent.objects.filter(
                article_grouper__app_config=self.app_config,
                versions__content_type=content_type_ac,
                versions__state=PUBLISHED
            ).values('pk')
        )

        categories_with_counts = (
            Category.objects.active_translations(languages[0])
            .filter(
                articlecontent__article_grouper__app_config=self.app_config,
                articlecontent__pk__in=published_content_pks_subquery,
            )
            .annotate(
                article_count=Count(
                    'articlecontent',
                    filter=Q(articlecontent__pk__in=published_content_pks_subquery),
                )
            )
            .filter(article_count__gt=0)
            .order_by('-article_count', 'translations__name')
            .distinct()
        )
        # Ordering uses translations__name so categories with the same count
        # appear alphabetically in the current language.

        return list(categories_with_counts)


class NewsBlogFeaturedArticlesPlugin(PluginEditModeMixin, NewsBlogCMSPlugin):
    article_count = models.PositiveIntegerField(
        default=1,
        validators=[django.core.validators.MinValueValidator(1)],
        help_text=_('The maximum number of featured articles display.')
    )

    def get_articles(self, request):
        if not self.article_count:
            return ArticleContent.objects.none()

        queryset = ArticleContent.objects.select_related(
            'article_grouper__app_config',
            'article_grouper__author',
            'featured_image'
        ).prefetch_related(
            'categories',
            'tags'
        ).filter(
            article_grouper__app_config=self.app_config,
            is_featured=True
        )

        languages = get_valid_languages_from_request(
            self.app_config.namespace, request)
        if self.language not in languages:
            # Ensure we return an empty queryset of the correct type
            return ArticleContent.objects.none()

        queryset = queryset.translated(*languages) # Apply language filter first

        if not self.get_edit_mode(request):
            content_type = ContentType.objects.get_for_model(ArticleContent)
            published_pks = CMSVersion.objects.filter(
                content_type=content_type,
                object_id__in=Subquery(queryset.values('pk')), # Use Subquery for efficiency
                state=PUBLISHED
            ).values_list('object_id', flat=True)
            queryset = queryset.filter(pk__in=published_pks)
        # In edit mode, we show all featured articles (published or not)
        # Potentially, ordering could differ in edit mode, e.g., by modification date of version
        # For now, the existing ordering (implicit or from Meta) will apply.
        # If specific ordering by version creation/publish date is needed, that's a further enhancement.

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
        languages = get_valid_languages_from_request(
            self.app_config.namespace, request)
        if self.language not in languages:
            return ArticleContent.objects.none()

        content_type = ContentType.objects.get_for_model(ArticleContent)
        edit_mode = self.get_edit_mode(request)

        # Base queryset for ArticleContent in the correct app_config and language
        base_queryset = ArticleContent.objects.select_related(
            'article_grouper__app_config',
            'article_grouper__author',
            'featured_image'
        ).filter(
            article_grouper__app_config=self.app_config
        ).translated(*languages)

        # Handle exclusion of featured articles
        excluded_pks = []
        if self.exclude_featured > 0:
            featured_qs = base_queryset.filter(is_featured=True)
            if not edit_mode:
                # Filter featured_qs by published versions
                published_featured_pks = CMSVersion.objects.filter(
                    content_type=content_type,
                    object_id__in=Subquery(featured_qs.values('pk')),
                    state=PUBLISHED
                ).values_list('object_id', flat=True)
                # We want to exclude these PKs
                excluded_pks = list(published_featured_pks[:self.exclude_featured])
            else:
                # In edit mode, exclude based on any featured version
                excluded_pks = list(featured_qs.values_list('pk', flat=True)[:self.exclude_featured])

        queryset = base_queryset.exclude(pk__in=excluded_pks)

        if not edit_mode:
            # Filter by published versions and order by publishing date
            # The 'created' timestamp of the PUBLISHED Version record is used as the publishing date.
            published_versions_subquery = CMSVersion.objects.filter(
                content_type=content_type,
                object_id=OuterRef('pk'),
                state=PUBLISHED
            ).order_by('-created') # Get the latest published version for an object_id if multiple (should not happen for PUBLISHED)

            queryset = queryset.annotate(
                publish_date=Subquery(published_versions_subquery.values('created')[:1])
            ).filter(
                publish_date__isnull=False # Ensure it has a published version
            ).order_by('-publish_date')
        else:
            # In edit mode, show all (published or not), perhaps ordered by grouper PK or content PK
            # Or by version creation date if available directly on content (less likely)
            # The existing Meta.ordering is ['-article_grouper__pk'] which is a reasonable default for edit mode.
            # If we want to order by *version* creation time, that's more complex.
            # For now, relying on default ordering or explicitly setting one.
            queryset = queryset.order_by('-article_grouper__pk') # Example explicit ordering for edit mode

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
        # FIXME comment can be removed after review, logic seems mostly sound.
        if not article or not hasattr(article, 'article_grouper'):
            return ArticleContent.objects.none()

        languages = get_valid_languages_from_request(
            article.article_grouper.app_config.namespace, request)
        if self.language not in languages:
            return ArticleContent.objects.none()

        related_groupers = article.related.all()

        queryset = ArticleContent.objects.select_related(
            'article_grouper__app_config',
            'article_grouper__author',
            'featured_image'
        ).prefetch_related(
            'categories',
            'tags'
        ).filter(
            article_grouper__in=related_groupers
        ).translated(*languages) # Apply language filter first

        if not self.get_edit_mode(request):
            # Imports should be at the top of the file generally
            # from django.contrib.contenttypes.models import ContentType # Already imported at top
            # from djangocms_versioning.constants import PUBLISHED # Already imported at top
            # from djangocms_versioning.models import Version # Already imported as CMSVersion at top

            ct = ContentType.objects.get_for_model(ArticleContent)
            # Use Subquery for consistency and potential performance
            published_pks = CMSVersion.objects.filter(
                content_type=ct,
                object_id__in=Subquery(queryset.values('pk')),
                state=PUBLISHED,
            ).values_list("object_id", flat=True)
            queryset = queryset.filter(pk__in=published_pks)
        # In edit mode, all related articles (published or not) are shown.
        # Ordering will depend on ArticleContent.Meta or can be made explicit if needed.
        return queryset

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
        # Using top-level imports: CMSVersion, PUBLISHED
        # ContentType, Count, Q, Subquery, Tag, TaggedItem, timezone are already imported or standard.
        from django.db.models import Count, Q # Subquery already imported
        from taggit.models import Tag, TaggedItem
        from django.utils import timezone

        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        # edit_mode = self.get_edit_mode(request) # Not used in this version of the query

        # 1. Get PKs of ArticleContent that are published AND belong to this plugin's app_config.
        # This subquery will find all object_ids (ArticleContent pks) that meet the criteria.
        published_content_in_appconfig_pks = Subquery(
            CMSVersion.objects.filter(
                content_type=content_type_ac,
                state=PUBLISHED,
                created__lte=timezone.now()
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
            taggit_taggeditem_items__pk__in=relevant_tagged_item_pks,  # Filter tags that are part of relevant items
        ).annotate(
            num_articles=Count(
                'taggit_taggeditem_items',
                filter=Q(taggit_taggeditem_items__pk__in=relevant_tagged_item_pks),
            )  # Count only the tagged items that are relevant (published, correct app_config, etc.)
        ).filter(num_articles__gt=0).order_by(
            '-num_articles', 'name'
        )  # Filter out tags with no articles after versioning filter

        # The above annotation should correctly count only the pre-filtered relevant_tagged_item_pks.
        # If performance is an issue or it's incorrect, the python loop below is a fallback.
        # For now, let's trust the annotation if possible.

        # Fallback Python-side counting (if complex annotation fails or is too slow):
        # relevant_tags_qs = Tag.objects.filter(
        #     pk__in=relevant_tagged_item_pks.values_list('tag_id', flat=True).distinct()
        # )
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

        final_tags = []
        for tag in tags_with_counts:
            tag.article_count = tag.num_articles
            final_tags.append(tag)
        return final_tags

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

    if ArticleContent.update_search_on_save and is_cms_plugin:  # Changed Article to ArticleContent
        placeholder = (
            getattr(instance, '_placeholder_cache', None) or instance.placeholder
        )  # noqa: W504
        if hasattr(placeholder, '_attached_model_cache'):
            if placeholder._attached_model_cache == ArticleContent:  # Changed Article to ArticleContent
                try:
                    # Ensure placeholder.pk is valid if placeholder comes from a just deleted plugin
                    if placeholder and placeholder.pk:
                        article_content = placeholder._attached_model_cache.objects.language(
                            instance.language
                        ).get(content=placeholder.pk)
                        current_language = instance.language or get_current_language()
                        # Pass request if available, needed by get_plugin_index_data.
                        # This might be problematic if request is not easily available here.
                        # Consider if get_search_data truly needs request or can work without it.
                        article_content.search_data = article_content.get_search_data(
                            current_language,
                            request=get_request(),
                        )
                        article_content.save()
                except ArticleContent.DoesNotExist:
                    pass  # ArticleContent might have been deleted


# Full implementation of the article_content_copy function

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
                new_content.slug = None  # Let it regenerate to avoid immediate unique constraint issues
                new_content.lead_in = original_translation.lead_in
                new_content.meta_title = original_translation.meta_title
                new_content.meta_description = original_translation.meta_description
                new_content.meta_keywords = original_translation.meta_keywords
                # search_data is auto-generated on save by get_search_data() if update_search_on_save is True
            new_content.save()  # This save will also trigger TranslatedAutoSlugifyMixin for slug

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
    new_content.related.set(original_content.related.all())  # related points to ArticleGrouper

    # 5. Copy placeholder plugins.
    # ``copy_plugins_to_placeholder`` handles most plugin types; warn if either
    # placeholder is missing.
    original_placeholder = original_content.content
    new_placeholder = new_content.content  # Accessing it should ensure it exists or is created

    if original_placeholder and new_placeholder:
        new_placeholder.clear()
        plugins = original_placeholder.get_plugins_list()
        copy_plugins_to_placeholder(plugins, new_placeholder)
    else:
        if not original_placeholder:
            warnings.warn(
                f"Original content {original_content.pk} has no placeholder 'content'.",
                RuntimeWarning,
            )
        if not new_placeholder:
            warnings.warn(
                f"New content {new_content.pk} could not get/create placeholder 'content'.",
                RuntimeWarning,
            )

# Return the duplicated instance
    return new_content


# ---------------------------------------------------------------------------
# Compatibility shims for newer djangocms-versioning APIs
from djangocms_versioning.models import Version, VersionQuerySet  # noqa: E402

if not hasattr(VersionQuerySet, "filter_by_content"):
    def filter_by_content(self, content):
        ct = ContentType.objects.get_for_model(type(content))
        return self.filter(content_type=ct, object_id=content.pk)

    VersionQuerySet.filter_by_content = filter_by_content
    Version.objects.filter_by_content = filter_by_content.__get__(Version.objects)
    ManagerCls = type(Version.objects)
    if not hasattr(ManagerCls, "filter_by_content"):
        def manager_filter_by_content(self, content):
            return self.get_queryset().filter_by_content(content)
        ManagerCls.filter_by_content = manager_filter_by_content

if not hasattr(VersionQuerySet, "filter_by_grouper"):
    def filter_by_grouper(self, grouper):
        content_type = ContentType.objects.get_for_model(ArticleContent)
        content_ids = ArticleContent._original_manager.filter(
            article_grouper=grouper
        ).values_list("pk", flat=True)
        return self.filter(content_type=content_type, object_id__in=content_ids)

    VersionQuerySet.filter_by_grouper = filter_by_grouper
    Version.objects.filter_by_grouper = filter_by_grouper.__get__(Version.objects)
    ManagerCls = type(Version.objects)
    if not hasattr(ManagerCls, "filter_by_grouper"):
        def manager_filter_by_grouper(self, grouper):
            return self.get_queryset().filter_by_grouper(grouper)
        ManagerCls.filter_by_grouper = manager_filter_by_grouper
