from typing import Optional

from django.contrib import admin
from django.urls.exceptions import NoReverseMatch
from django.utils.translation import gettext_lazy as _

from cms.admin.placeholderadmin import (
    FrontendEditableAdminMixin, PlaceholderAdminMixin,
)

from aldryn_apphooks_config.admin import BaseAppHookConfig, ModelAppHookConfig
from aldryn_people.models import Person
from aldryn_translation_tools.admin import AllTranslationsMixin
from parler.admin import TranslatableAdmin
from parler.forms import TranslatableModelForm

from . import models


def make_published(modeladmin, request, queryset):
    queryset.update(is_published=True)


make_published.short_description = _(
    "Mark selected articles as published")


def make_unpublished(modeladmin, request, queryset):
    queryset.update(is_published=False)


make_unpublished.short_description = _(
    "Mark selected articles as not published")


def make_featured(modeladmin, request, queryset):
    queryset.update(is_featured=True)


make_featured.short_description = _(
    "Mark selected articles as featured")


def make_not_featured(modeladmin, request, queryset):
    queryset.update(is_featured=False)


make_not_featured.short_description = _(
    "Mark selected articles as not featured")


class ArticleAdminForm(TranslatableModelForm):

    class Meta:
        model = models.ArticleContent # Changed from Article
        fields = [
            'article_grouper', # Added: field to link to the grouper
            'title',
            'slug',
            'lead_in',
            'featured_image',
            'is_featured', # Kept: as it's a content-specific flag
            'categories',
            'tags',
            'related', # Kept: now points to ArticleGrouper
            'meta_title',
            'meta_description',
            'meta_keywords',
            # Removed: app_config, owner, author (on grouper)
            # Removed: is_published, publishing_date (versioning)
            # Removed: serial, episode (on grouper)
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The 'related' field on ArticleContent now points to ArticleGrouper.
        # So, the queryset should be for ArticleGrouper.
        if 'related' in self.fields:
            qs = models.ArticleGrouper.objects.all()
            if self.instance and hasattr(self.instance, 'article_grouper') and self.instance.article_grouper_id:
                # Exclude the current article's own grouper from related choices.
                qs = qs.exclude(pk=self.instance.article_grouper_id)
            self.fields['related'].queryset = qs
            # Prevent adding new related items (groupers) directly from this form's widget.
            if hasattr(self.fields['related'], 'widget'):
                self.fields['related'].widget.can_add_related = False

        # Fields like 'app_config', 'author', 'owner', 'serial', 'episode' are now on ArticleGrouper.
        # If they need to be set, it would typically be done when creating/editing the ArticleGrouper,
        # not the ArticleContent directly (or ArticleContent form would need to handle this indirectly).
        # Thus, direct manipulation of self.fields['app_config'] or self.fields['author'] is removed here.


@admin.register(models.ArticleContent) # Changed from models.Article and ArticleAdmin
class ArticleContentAdmin( # Renamed from ArticleAdmin
    AllTranslationsMixin,
    PlaceholderAdminMixin,
    FrontendEditableAdminMixin,
    ModelAppHookConfig,
    TranslatableAdmin
):
    form = ArticleAdminForm
    # Updated list_display: removed app_config, is_published. Added article_grouper related fields.
    list_display = ('title', 'slug', 'is_featured_display', 'article_grouper_app_config_display', 'language_column')
    # Updated list_filter: use fields from ArticleGrouper. Removed publishing_date.
    list_filter = (
        'article_grouper__app_config',
        'categories',
        'is_featured', # is_featured is on ArticleContent
        'article_grouper__author', # Author is on grouper
    )
    # actions related to is_published are removed as this is handled by versioning.
    # is_featured actions can remain if is_featured is managed independently.
    actions = (
        make_featured, make_not_featured,
        # make_published, make_unpublished, # Removed
    )
    # date_hierarchy = 'publishing_date' # Removed

    # Updated fieldsets:
    fieldsets = (
        (None, {
            'fields': (
                'article_grouper', # Link to the grouper
                'title',
                'is_featured', # is_featured is on ArticleContent
                'lead_in',
                # 'content', # PlaceholderField usually handled by PlaceholderAdminMixin separately
            )
        }),
        (_('Meta Options'), {
            'classes': ('collapse',),
            'fields': (
                'slug',
                'meta_title',
                'meta_description',
                'meta_keywords',
            )
        }),
        (_('Advanced Settings'), {
            'classes': ('collapse',),
            'fields': (
                'tags',
                'categories',
                'related', # related now points to ArticleGrouper
                'featured_image',
            )
        }),
    )
    filter_horizontal = [
        'categories',
        # 'related', # SortedManyToManyField might not work well with filter_horizontal by default with groupers
    ]
    # app_config_values: 'is_published' removed. This needs review with versioning.
    # app_config_values = {
    #     'default_published': 'is_published' # This is no longer valid
    # }
    app_config_selection_title = '' # These might be fine if ModelAppHookConfig is still used by grouper admin
    app_config_selection_desc = ''

    def article_grouper_app_config_display(self, obj):
        if obj.article_grouper:
            return obj.article_grouper.app_config
        return None
    article_grouper_app_config_display.short_description = _('App Config')
    article_grouper_app_config_display.admin_order_field = 'article_grouper__app_config'

    def is_featured_display(self, obj): # Renamed to avoid conflict if base class has it
        return obj.is_featured
    is_featured_display.short_description = _('Is Featured')
    is_featured_display.boolean = True
    is_featured_display.admin_order_field = 'is_featured'


    # add_view: Pre-filling author/owner is now relevant for ArticleGrouper, not ArticleContent.
    # This method might need to be removed or adapted if ArticleContent is created inline with ArticleGrouper.
    # For a standalone ArticleContent admin, pre-filling these doesn't make sense as they are on the grouper.
    # def add_view(self, request, *args, **kwargs):
    #     data = request.GET.copy()
    #     # Logic for author and owner pre-fill removed
    #     return super().add_view(request, *args, **kwargs)

    def get_view_on_site_url(self, obj=None) -> Optional[str]:
        if obj is not None:
            try:
                obj.get_absolute_url()
            except NoReverseMatch:
                # This occurs when Aldryn News section is not published on the site.
                # 'aldryn_newsblog_default' is not a registered namespace
                return None
        return super().get_view_on_site_url(obj)


class SerialAdmin(admin.ModelAdmin):
    list_display = ('name', 'episodes_count')
    change_form_template = "aldryn_newsblog/admin/serial_episodes_change_form.html"

    def episodes_count(self, obj: models.Serial) -> int:
        # Article was renamed to ArticleContent, serial is on ArticleGrouper
        return models.ArticleGrouper.objects.filter(serial=obj).count()
    episodes_count.short_description = _('Total episodes')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if extra_context is None:
            extra_context = {}
        # Article was renamed to ArticleContent, serial and episode are on ArticleGrouper
        # To display episodes (ArticleContent), we'd query through ArticleGrouper
        extra_context['serial_episodes'] = models.ArticleContent.objects.filter(
            article_grouper__serial_id=object_id
        ).order_by('article_grouper__episode') # Order by episode on the grouper
        return self.changeform_view(request, object_id, form_url, extra_context)

# admin.site.register(models.Article, ArticleAdmin) # Removed, ArticleContentAdmin registered with decorator
admin.site.register(models.Serial, SerialAdmin)


class NewsBlogConfigAdmin(
    AllTranslationsMixin,
    PlaceholderAdminMixin,
    BaseAppHookConfig,
    TranslatableAdmin
):
    def get_config_fields(self):
        return (
            'app_title', 'permalink_type', 'non_permalink_handling',
            'template_prefix', 'paginate_by', 'pagination_pages_start',
            'pagination_pages_visible', 'exclude_featured',
            'create_authors', 'hide_author', 'author_no_photo', 'search_indexed', 'config.default_published',
        )


admin.site.register(models.NewsBlogConfig, NewsBlogConfigAdmin)
