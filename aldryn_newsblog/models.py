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
            unique=True, # Make slug unique per language again
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
        # meta={'unique_together': (('language_code', 'article_grouper', 'slug',),)}, # Moved to main Meta

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

        # FIXME #VERSIONING: This import might be better at the top of the file.
        from djangocms_versioning.models import Version
        # from django.utils.timezone import now # now is already imported from django.utils.timezone

        try:
            # Get the version object associated with this content instance
            version = Version.objects.get_for_content(self)
            if version and version.published: # Check if a published version exists
                publishing_date = version.published.date() # Get the date part of the publish datetime
            else:
                # Fallback if no published version found or not yet published (e.g., a draft)
                # The URL might not be truly "absolute" or canonical for a draft.
                # Using current date might be misleading. Consider raising an error or returning a non-date based URL if appropriate.
                # For now, to avoid breaking URL generation entirely for drafts if they call this:
                publishing_date = now().date() # Or handle as an error/None if permalink_type needs date
                # FIXME #VERSIONING: Decide how to handle get_absolute_url for non-published versions.
                # This might depend on how previews and draft URLs are constructed by djangocms-versioning.
        except Version.DoesNotExist:
            # Fallback if no version object at all (should ideally not happen for versioned content)
            publishing_date = now().date() # Or handle as an error
            # FIXME #VERSIONING: Handle missing Version object case.

        if 'y' in permalink_type:
            kwargs.update(year=publishing_date.year)
        if 'm' in permalink_type:
            kwargs.update(month="%02d" % publishing_date.month)
        if 'd' in permalink_type:
            kwargs.update(day="%02d" % publishing_date.day)
        if 'i' in permalink_type:
            # The PK in the URL could be the grouper's PK or the content's PK
            # depending on strategy. Let's assume grouper PK for now.
            kwargs.update(pk=self.article_grouper.pk)
        if 's' in permalink_type:
            slug, lang = self.known_translation_getter(
                'slug', default=None, language_code=language)
            if slug and lang:
                site_id = getattr(settings, 'SITE_ID', None)
                if get_redirect_on_fallback(language, site_id):
                    language = lang
                kwargs.update(slug=slug)

        # app_config is now on the grouper
        if self.article_grouper.app_config and self.article_grouper.app_config.namespace:
            namespace = f'{self.article_grouper.app_config.namespace}:'
        else:
            namespace = ''

        with override(language):
            # The URL name might need to change if it implies a specific model,
            # but for now, assume 'article-detail' refers to the concept of an article.
            return reverse(f'{namespace}article-detail', kwargs=kwargs)

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
        # FIXME: This SQL needs full review with versioning.
        # It should count published ArticleContent versions grouped by author on ArticleGrouper.
        subquery = """
            SELECT COUNT(DISTINCT grouper.id)
            FROM aldryn_people_person AS person
            INNER JOIN aldryn_newsblog_articlegrouper AS grouper ON person.id = grouper.author_id
            WHERE grouper.app_config_id = %s AND person.id = aldryn_people_person.id"""
            # Published state check (via Version model) needs to be added here.

        # For other users, limit subquery to published articles
        if not self.get_edit_mode(request):
            # FIXME: This part needs to integrate with djangocms-versioning state.
            # For now, this condition is effectively removed, making counts potentially inaccurate.
            # subquery += """ AND EXISTS (SELECT 1 FROM djangocms_versioning_version v
            # JOIN aldryn_newsblog_articlecontent ac ON v.object_id = ac.id
            # WHERE v.content_type_id = (SELECT id FROM django_content_type WHERE model = 'articlecontent')
            # AND ac.article_grouper_id = grouper.id AND v.state = 'published')"""
            pass  # Placeholder for versioning check

        # Now, use this subquery in the construction of the main query.
        query = """
            SELECT person.*, ({}) as article_count
            FROM aldryn_people_person AS person
        """.format(subquery % (self.app_config.pk, )) # Pass app_config.pk to subquery

        raw_authors = list(Person.objects.raw(query))
        authors = [author for author in raw_authors if hasattr(author, 'article_count') and author.article_count > 0]
        return sorted(authors, key=lambda x: x.article_count, reverse=True)

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

        # FIXME: This SQL needs full review with versioning.
        # It should count published ArticleContent versions per category.
        subquery = """
            SELECT COUNT(DISTINCT content.id)
            FROM aldryn_categories_category AS cat
            INNER JOIN aldryn_newsblog_articlecontent_categories AS content_cat ON cat.id = content_cat.category_id
            INNER JOIN aldryn_newsblog_articlecontent AS content ON content_cat.articlecontent_id = content.id
            INNER JOIN aldryn_newsblog_articlegrouper AS grouper ON content.article_grouper_id = grouper.id
            WHERE grouper.app_config_id = %s AND cat.id = aldryn_categories_category.id"""
            # Published state check (via Version model) needs to be added here.

        if not self.get_edit_mode(request):
            # FIXME: This part needs to integrate with djangocms-versioning state.
            pass  # Placeholder for versioning check

        query = """
            SELECT cat.*, ({}) as article_count
            FROM aldryn_categories_category AS cat
        """.format(subquery % (self.app_config.pk,))

        raw_categories = list(Category.objects.raw(query))
        categories = [
            category for category in raw_categories if hasattr(category, 'article_count') and category.article_count > 0]
        return sorted(categories, key=lambda x: x.article_count, reverse=True)


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
        # FIXME: This SQL needs full review with versioning.
        # Tags are on ArticleContent. Published state needs to be derived from Version model.
        article_content_type = ContentType.objects.get_for_model(ArticleContent)

        subquery = """
            SELECT COUNT(DISTINCT content.id)
            FROM taggit_tag AS tag
            INNER JOIN taggit_taggeditem AS tagged_item ON tag.id = tagged_item.tag_id
            INNER JOIN aldryn_newsblog_articlecontent AS content ON tagged_item.object_id = content.id AND tagged_item.content_type_id = %s
            INNER JOIN aldryn_newsblog_articlegrouper AS grouper ON content.article_grouper_id = grouper.id
            WHERE grouper.app_config_id = %s AND tag.id = taggit_tag.id"""
            # Published state check (via Version model) needs to be added here.

        if not self.get_edit_mode(request):
            # FIXME: This part needs to integrate with djangocms-versioning state.
            pass  # Placeholder for versioning check

        query = """
            SELECT tag.*, ({}) as article_count
            FROM taggit_tag AS tag
        """.format(subquery % (article_content_type.id, self.app_config.pk))

        raw_tags = list(Tag.objects.raw(query))
        tags = [tag for tag in raw_tags if hasattr(tag, 'article_count') and tag.article_count > 0]
        return sorted(tags, key=lambda x: x.article_count, reverse=True)

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
    # FIXME #VERSIONING: Placeholder copying can be complex, especially with nested plugins.
    # djangocms-versioning might handle some of this automatically for registered PlaceholderFields.
    # If not, a manual copy like below is a common pattern.
    original_placeholder = original_content.content
    new_placeholder = new_content.content # Accessing it should ensure it exists or is created

    if original_placeholder and new_placeholder:
        # It's generally safer to clear the new placeholder if it might have default plugins,
        # though for a fresh instance via _original_manager.create(), it should be empty.
        new_placeholder.clear()
        plugins = original_placeholder.get_plugins_list()
        for plugin_base in plugins:
            # Create a new plugin instance by copying from the original.
            # This relies on each plugin's own copy_plugin method or similar logic
            # if it has one, or add_plugin's behavior for basic plugins.
            # For complex plugins, more specific handling might be needed.
            # Using _no_reorder to prevent add_plugin from trying to fix tree ordering yet.
            opts = {
                key: getattr(plugin_base, key)
                for key in plugin_base.copy_ μεταξύ_fields
                if hasattr(plugin_base, key)
            }
            # Remove position as it will be recalculated
            opts.pop("position", None)
            # If parent_id is in copy_fields, it needs careful handling for nested plugins
            # For now, assuming add_plugin handles basic parent assignment if needed for flat copies.
            # This part is highly complex for deeply nested plugins and might need a recursive copy.

            # A simpler approach if plugin_base.attributes gives all necessary serializable fields:
            # instance_data = plugin_base.attributes
            # instance_data.update(plugin_base.get_bound_plugin().get_plugin_instance_data())

            # For now, let's try a basic add_plugin and assume copy_relations handles most cases
            # This is a known difficult part of content copying in django-cms.
            # The most robust solution often involves cms.api.copy_plugins_to_placeholder if available and applicable.

            # Simplified approach:
            new_plugin_instance = add_plugin(
                placeholder=new_placeholder,
                plugin_type=plugin_base.plugin_type,
                language=plugin_base.language,
                **plugin_base.attributes, # Pass attributes from original plugin
            )
            # If the plugin has child plugins, they need to be copied recursively.
            # This basic add_plugin won't do that.
            # FIXME: Implement recursive plugin copy if needed.
    else:
        if not original_placeholder:
            print(f"Warning: Original content {original_content.pk} has no placeholder 'content'.")
        if not new_placeholder:
            print(f"Warning: New content {new_content.pk} could not get/create placeholder 'content'.")

    return new_content
