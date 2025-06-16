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
from .models import ArticleGrouper # Ensure ArticleGrouper is imported

from cms.admin.utils import GrouperModelAdmin
from djangocms_versioning.admin import ExtendedGrouperVersionAdminMixin, StateIndicatorMixin, ExtendedVersionAdminMixin


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


@admin.register(ArticleGrouper)
class ArticleGrouperAdmin(ExtendedGrouperVersionAdminMixin, StateIndicatorMixin, GrouperModelAdmin):
    content_model = models.ArticleContent # Explicitly set the content model
    list_display = [
        '__str__',
        'author',
        'app_config',
        'state_indicator', # From StateIndicatorMixin
        'serial',
        'episode',
    ]
    list_filter = [
        'app_config',
        'author',
        'serial',
    ]
    search_fields = ['author__name', 'serial__name', 'translations__title'] # Example, assuming title on content


@admin.register(models.ArticleContent) # Changed from models.Article and ArticleAdmin
class ArticleContentAdmin( # Renamed from ArticleAdmin
    ExtendedVersionAdminMixin, # Added
    AllTranslationsMixin,
    PlaceholderAdminMixin,
    FrontendEditableAdminMixin,
    # ModelAppHookConfig, # Commented out as app_config is on grouper
    TranslatableAdmin
):
    form = ArticleAdminForm
    # list_display, list_filter, and actions are typically managed by ExtendedVersionAdminMixin
    # or are less relevant for a version edit screen.
    # Commenting them out for now.
    # list_display = ('title', 'slug', 'is_featured_display', 'article_grouper_app_config_display', 'language_column')
    # list_filter = (
    #     'article_grouper__app_config',
    #     'categories',
    #     'is_featured',
    #     'article_grouper__author',
    # )
    # actions = (
    #     make_featured, make_not_featured,
    # )

    # fieldsets define the edit view for a version (ArticleContent)
    fieldsets = (
        (None, {
            'fields': (
                # 'article_grouper', # Should NOT be editable here; it's fixed for a version.
                                   # ExtendedVersionAdminMixin handles this link.
                'title',
                'is_featured',
                'lead_in',
                # 'content', # PlaceholderField handled by PlaceholderAdminMixin
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
                'related',
                'featured_image',
            )
        }),
    )
    filter_horizontal = [
        'categories',
        'related', # related pointing to ArticleGrouper might work here.
    ]

    # Remove methods specific to the old list display or ModelAppHookConfig if it was removed.
    # The display methods like 'article_grouper_app_config_display' are for list_display.
    # 'add_view' might not be directly used if versions are created via grouper admin.
    # 'get_view_on_site_url' is useful and ExtendedVersionAdminMixin might provide its own or enhance this.
    # For now, keeping get_view_on_site_url as it might still be relevant for viewing a specific version.
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
