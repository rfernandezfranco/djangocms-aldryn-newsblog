from datetime import date, datetime

from django.db.models import Q
from django.http import (
    Http404, HttpResponsePermanentRedirect, HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.utils import translation
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.contrib.contenttypes.models import ContentType # Added for versioning queries
from djangocms_versioning.models import Version # Added for versioning queries
from djangocms_versioning.constants import PUBLISHED # Added for versioning queries
from django.db.models import OuterRef, Subquery, Q # Added for subqueries, Q was already there

from menus.utils import set_language_changer

from aldryn_apphooks_config.mixins import AppConfigMixin
from aldryn_categories.models import Category
from aldryn_people.models import Person
from dateutil.relativedelta import relativedelta
from parler.views import TranslatableSlugMixin, ViewUrlMixin
from taggit.models import Tag

from aldryn_newsblog.compat import toolbar_edit_mode_active
from aldryn_newsblog.utils.utilities import get_valid_languages_from_request

from .models import ArticleContent, ArticleGrouper # Changed Article to ArticleContent, ArticleGrouper
from .utils import add_prefix_to_path


class TemplatePrefixMixin:

    def prefix_template_names(self, template_names):
        if (hasattr(self.config, 'template_prefix') and  # noqa: W504
                self.config.template_prefix):
            prefix = self.config.template_prefix
            template_names = [
                add_prefix_to_path(template, prefix) for template in template_names
            ] + template_names
        return template_names

    def get_template_names(self):
        template_names = super().get_template_names()
        return self.prefix_template_names(template_names)


class EditModeMixin:
    """
    A mixin which sets the property 'edit_mode' with the truth value for
    whether a user is logged-into the CMS and is in edit-mode.
    """
    edit_mode = False

    def dispatch(self, request, *args, **kwargs):
        self.edit_mode = (
            self.request.toolbar and toolbar_edit_mode_active(self.request))
        return super().dispatch(request, *args, **kwargs)


class PreviewModeMixin(EditModeMixin):
    """
    If content editor is logged-in, show all articles. Otherwise, only the
    published articles should be returned.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        # check if user can see unpublished items. this will allow to switch
        # to edit mode instead of 404 on article detail page. CMS handles the
        # permissions.
        user = self.request.user
        user_can_edit = user.is_staff or user.is_superuser
        if not (self.edit_mode or user_can_edit):
            # Relying on djangocms-versioning's default manager to filter for published versions.
            # If user_can_edit or in edit_mode, versioning system may show drafts.
            pass # No explicit filtering here if default manager is version-aware.
        language = translation.get_language()
        # FIXME #VERSIONING: .namespace() needs adjustment if it relied on Article structure.
        # It should now filter based on article_grouper.app_config.namespace.
        # Assuming self.namespace is the namespace string from the apphook.
        if hasattr(self, 'namespace') and self.namespace:
             qs = qs.filter(article_grouper__app_config__namespace=self.namespace)
        qs = qs.active_translations(language)
        return qs


class AppHookCheckMixin:

    def dispatch(self, request, *args, **kwargs):
        self.valid_languages = get_valid_languages_from_request(
            self.namespace, request)
        return super().dispatch(
            request, *args, **kwargs)

    def get_queryset(self):
        # filter available objects to contain only resolvable for current
        # language. IMPORTANT: after .translated - we cannot use .filter
        # on translated fields (parler/django limitation).
        # if your mixin contains filtering after super call - please place it
        # after this mixin.
        qs = super().get_queryset()
        return qs.translated(*self.valid_languages)


class ArticleDetail(AppConfigMixin, AppHookCheckMixin, PreviewModeMixin,
                    TranslatableSlugMixin, TemplatePrefixMixin, DetailView):
    model = ArticleContent # Changed Article to ArticleContent
    slug_field = 'slug'
    year_url_kwarg = 'year'
    month_url_kwarg = 'month'
    day_url_kwarg = 'day'
    slug_url_kwarg = 'slug'
    pk_url_kwarg = 'pk'

    def get(self, request, *args, **kwargs):
        """
        This handles non-permalinked URLs according to preferences as set in
        NewsBlogConfig.
        """
        if not hasattr(self, 'object'):
            self.object = self.get_object()
        set_language_changer(request, self.object.get_absolute_url)
        url = self.object.get_absolute_url()
        if self.config.non_permalink_handling == 200 or request.path == url:
            # Continue as normal
            return super().get(request, *args, **kwargs)

        # Check to see if the URL path matches the correct absolute_url of
        # the found object
        if self.config.non_permalink_handling == 302:
            return HttpResponseRedirect(url)
        elif self.config.non_permalink_handling == 301:
            return HttpResponsePermanentRedirect(url)
        else:
            raise Http404('This is not the canonical uri of this object.')

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        """
        Supports ALL of the types of permalinks that we've defined in urls.py.
        However, it does require that either the id and the slug is available
        and unique.
        """
        if queryset is None:
            queryset = self.get_queryset()

        slug = self.kwargs.get(self.slug_url_kwarg, None)
        pk = self.kwargs.get(self.pk_url_kwarg, None)

        if pk is not None:
            # Let the DetailView itself handle this one
            return DetailView.get_object(self, queryset=queryset)
        elif slug is not None:
            # Let the TranslatedSlugMixin take over
            return super().get_object(queryset=queryset)

        raise AttributeError('ArticleDetail view must be called with either '
                             'an object pk or a slug')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['prev_article'] = self.get_prev_object(
            self.queryset, self.object)
        context['next_article'] = self.get_next_object(
            self.queryset, self.object)
        if self.config is not None:
            context['aldryn_newsblog_display_author_no_photo'] = self.config.author_no_photo
            context['aldryn_newsblog_hide_author'] = self.config.hide_author
            context['aldryn_newsblog_template_prefix'] = self.config.template_prefix
        return context

    def get_prev_object(self, queryset=None, object=None):
        if queryset is None:
            queryset = self.get_queryset()
        if queryset is None:
            queryset = self.get_queryset() # This queryset is of ArticleContent
        if object is None:
            object = self.get_object() # Current ArticleContent instance

        try:
            current_version = Version.objects.get_for_content(object)
            if not current_version or not current_version.published:
                return None # No published version for current object, so no prev/next
            current_published_date = current_version.published
        except Version.DoesNotExist:
            return None # Should not happen for a displayed object

        # Subquery to get the published date of a version for an ArticleContent
        version_published_subquery = Version.objects.filter(
            object_id=OuterRef('pk'),
            content_type=ContentType.objects.get_for_model(ArticleContent),
            state=PUBLISHED
        ).values('published')[:1]

        qs_with_version_date = queryset.annotate(
            version_published_date=Subquery(version_published_subquery)
        ).exclude(version_published_date__isnull=True) # Ensure we only consider items with a published version

        prev_objs = qs_with_version_date.filter(
            version_published_date__lt=current_published_date
        ).order_by('-version_published_date')[:1]

        return prev_objs[0] if prev_objs else None

    def get_next_object(self, queryset=None, object=None):
        if queryset is None:
            queryset = self.get_queryset()
        if object is None:
            object = self.get_object()

        try:
            current_version = Version.objects.get_for_content(object)
            if not current_version or not current_version.published:
                return None
            current_published_date = current_version.published
        except Version.DoesNotExist:
            return None

        version_published_subquery = Version.objects.filter(
            object_id=OuterRef('pk'),
            content_type=ContentType.objects.get_for_model(ArticleContent),
            state=PUBLISHED
        ).values('published')[:1]

        qs_with_version_date = queryset.annotate(
            version_published_date=Subquery(version_published_subquery)
        ).exclude(version_published_date__isnull=True)

        next_objs = qs_with_version_date.filter(
            version_published_date__gt=current_published_date
        ).order_by('version_published_date')[:1]

        return next_objs[0] if next_objs else None


class ArticleListBase(AppConfigMixin, AppHookCheckMixin, TemplatePrefixMixin,
                      PreviewModeMixin, ViewUrlMixin, ListView):
    model = ArticleContent # Changed Article to ArticleContent
    show_header = False

    def get_paginate_by(self, queryset):
        if self.paginate_by is not None:
            return self.paginate_by
        else:
            try:
                return self.config.paginate_by
            except AttributeError:
                return 10  # sensible failsafe

    def get_pagination_options(self):
        # Django does not handle negative numbers well
        # when using variables.
        # So we perform the conversion here.
        if self.config:
            options = {
                'pages_start': self.config.pagination_pages_start,
                'pages_visible': self.config.pagination_pages_visible,
            }
        else:
            options = {
                'pages_start': 10,
                'pages_visible': 4,
            }

        pages_visible_negative = -options['pages_visible']
        options['pages_visible_negative'] = pages_visible_negative
        options['pages_visible_total'] = options['pages_visible'] + 1
        options['pages_visible_total_negative'] = pages_visible_negative - 1
        return options

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pagination'] = self.get_pagination_options()
        if self.config is not None:
            context['aldryn_newsblog_display_author_no_photo'] = self.config.author_no_photo
            context['aldryn_newsblog_hide_author'] = self.config.hide_author
            context['aldryn_newsblog_template_prefix'] = self.config.template_prefix
        return context


class ArticleList(ArticleListBase):
    """A complete list of articles."""
    show_header = True

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.config is not None:
            # exclude featured articles from queryset, to allow featured article
            # plugin on the list view page without duplicate entries in page qs.
            exclude_count = self.config.exclude_featured
            if exclude_count:
                # FIXME #VERSIONING: .published() needs re-evaluation. is_featured is on ArticleContent.
                # This needs to get PKs of ArticleContent that are featured and published (via versioning).
                featured_qs = ArticleContent.objects.filter(
                    article_grouper__app_config=self.config, # Assuming self.config is the app_config instance
                    is_featured=True
                )
                # if not self.edit_mode:
                #    featured_qs = featured_qs.published() # Placeholder for versioning's published filter
                exclude_featured_pks = featured_qs.values_list('pk', flat=True)[:exclude_count]
                qs = qs.exclude(pk__in=exclude_featured_pks)
        return qs


class ArticleSearchResultsList(ArticleListBase):
    # model = ArticleContent is inherited from ArticleListBase
    http_method_names = ['get', 'post', ]
    partial_name = 'aldryn_newsblog/includes/search_results.html'
    template_name = 'aldryn_newsblog/article_list.html'

    def get(self, request, *args, **kwargs):
        self.query = request.GET.get('q')
        self.max_articles = request.GET.get('max_articles', 0)
        self.edit_mode = (request.toolbar and toolbar_edit_mode_active(request))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)

    def get_paginate_by(self, queryset):
        """
        If a max_articles was set (by a plugin), use that figure, else,
        paginate by the app_config's settings.
        """
        return self.max_articles or super().get_paginate_by(self.get_queryset())

    def get_queryset(self):
        qs = super().get_queryset()
        # if not self.edit_mode:
            # FIXME #VERSIONING: .published() needs re-evaluation
            # qs = qs.published()
        if self.query:
            # search_data is on ArticleContent's translations.
            # title and lead_in are also on translations.
            return qs.filter(
                Q(translations__title__icontains=self.query) |  # noqa: #W504
                Q(translations__lead_in__icontains=self.query) |  # noqa: #W504
                Q(translations__search_data__icontains=self.query)
            ).distinct()
        else:
            return qs.none()

    def get_context_data(self, **kwargs):
        cxt = super().get_context_data(**kwargs)
        cxt['query'] = self.query
        return cxt

    def get_template_names(self):
        if self.request.is_ajax:
            template_names = [self.partial_name]
        else:
            template_names = [self.template_name]
        return self.prefix_template_names(template_names)


class AuthorArticleList(ArticleListBase):
    """A list of articles written by a specific author."""
    def get_queryset(self):
        # author is now on ArticleGrouper.
        return super().get_queryset().filter(
            article_grouper__author=self.author
        )

    def get(self, request, author, *args, **kwargs):
        language = translation.get_language_from_request(
            request, check_path=True)
        self.author = Person.objects.language(language).active_translations(
            language, slug=author).first()
        if not self.author:
            raise Http404('Author not found')
        return super().get(request, *args, **kwargs)

    def post(self, request, author, *args, **kwargs):
        return self.get(request, author, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs['newsblog_author'] = self.author
        return super().get_context_data(**kwargs)


class CategoryArticleList(ArticleListBase):
    """A list of articles filtered by categories."""
    def get_queryset(self):
        return super().get_queryset().filter(
            categories=self.category
        )

    def get(self, request, category, *args, **kwargs):
        self.category = get_object_or_404(
            Category, translations__slug=category)
        return super().get(request, *args, **kwargs)

    def post(self, request, category, *args, **kwargs):
        return self.get(request, category, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs['newsblog_category'] = self.category
        ctx = super().get_context_data(**kwargs)
        ctx['newsblog_category'] = self.category
        return ctx


class TagArticleList(ArticleListBase):
    """A list of articles filtered by tags."""
    def get_queryset(self):
        return super().get_queryset().filter(
            tags=self.tag
        )

    def get(self, request, tag, *args, **kwargs):
        self.tag = get_object_or_404(Tag, slug=tag)
        return super().get(request, *args, **kwargs)

    def post(self, request, tag, *args, **kwargs):
        return self.get(request, tag, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs['newsblog_tag'] = self.tag
        return super().get_context_data(**kwargs)


class DateRangeArticleList(ArticleListBase):
    """A list of articles for a specific date range"""
    def get_queryset(self):
        qs = super().get_queryset() # Base queryset of ArticleContent

        # FIXME #VERSIONING: This assumes super().get_queryset() ALREADY filters by published state
        # due to djangocms-versioning's default manager. If not, this needs to be more robust.
        # The filtering here is specifically for the date range based on the Version's published field.

        content_type = ContentType.objects.get_for_model(ArticleContent)
        # Subquery to find object_ids of ArticleContent that have a published version within the date range.
        # Using .values('object_id') and distinct based on typical versioning patterns.
        version_object_ids_in_range = Version.objects.filter(
            content_type=content_type,
            state=PUBLISHED, # Ensure we are looking at the published version's date
            published__gte=self.date_from,
            published__lt=self.date_to
        ).values_list('object_id', flat=True).distinct()

        # Filter the main queryset to include only those ArticleContent items.
        qs = qs.filter(pk__in=Subquery(version_object_ids_in_range)) # Using Subquery directly on values_list

        return qs

    def _daterange_from_kwargs(self, kwargs):
        raise NotImplementedError('Subclasses of DateRangeArticleList need to'
                                  'implement `_daterange_from_kwargs`.')

    def get(self, request, *args, **kwargs):
        self.date_from, self.date_to = self._daterange_from_kwargs(kwargs)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs['newsblog_day'] = (
            int(self.kwargs.get('day')) if 'day' in self.kwargs else None)
        kwargs['newsblog_month'] = (
            int(self.kwargs.get('month')) if 'month' in self.kwargs else None)
        kwargs['newsblog_year'] = (
            int(self.kwargs.get('year')) if 'year' in self.kwargs else None)
        if kwargs['newsblog_year']:
            kwargs['newsblog_archive_date'] = date(
                kwargs['newsblog_year'],
                kwargs['newsblog_month'] or 1,
                kwargs['newsblog_day'] or 1)
        return super().get_context_data(**kwargs)


class YearArticleList(DateRangeArticleList):
    def _daterange_from_kwargs(self, kwargs):
        date_from = datetime(int(kwargs['year']), 1, 1)
        date_to = date_from + relativedelta(years=1)
        return date_from, date_to


class MonthArticleList(DateRangeArticleList):
    def _daterange_from_kwargs(self, kwargs):
        date_from = datetime(int(kwargs['year']), int(kwargs['month']), 1)
        date_to = date_from + relativedelta(months=1)
        return date_from, date_to


class DayArticleList(DateRangeArticleList):
    def _daterange_from_kwargs(self, kwargs):
        date_from = datetime(
            int(kwargs['year']), int(kwargs['month']), int(kwargs['day']))
        date_to = date_from + relativedelta(days=1)
        return date_from, date_to
