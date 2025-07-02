from typing import Optional

from django.contrib import admin
from django.urls.exceptions import NoReverseMatch
from django.utils.translation import gettext_lazy as _

from cms.admin.placeholderadmin import (
    FrontendEditableAdminMixin, PlaceholderAdminMixin,
)

from aldryn_apphooks_config.admin import BaseAppHookConfig
from aldryn_people.models import Person
from aldryn_translation_tools.admin import AllTranslationsMixin
from parler.admin import TranslatableAdmin
from parler.forms import TranslatableModelForm
from django import forms
import datetime

from . import models
from .models import ArticleGrouper  # Ensure ArticleGrouper is imported

from cms.admin.utils import GrouperModelAdmin, CONTENT_PREFIX
from django.conf import settings
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
        model = models.ArticleContent  # Changed from Article
        fields = [
            'article_grouper',  # Added: field to link to the grouper
            'title',
            'slug',
            'lead_in',
            'featured_image',
            'is_featured',  # Kept: as it's a content-specific flag
            # M2M fields removed to avoid versioning create errors
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

    def get_initial_for_field(self, field, field_name):
        value = super().get_initial_for_field(field, field_name)
        if hasattr(value, 'all'):
            value = list(value.all())
        return value

        # Fields like 'app_config', 'author', 'owner', 'serial', 'episode' are now on ArticleGrouper.
        # If they need to be set, it would typically be done when creating/editing the ArticleGrouper,
        # not the ArticleContent directly (or ArticleContent form would need to handle this indirectly).
        # Thus, direct manipulation of self.fields['app_config'] or self.fields['author'] is removed here.


class ArticleGrouperAdminForm(forms.ModelForm):
    """ModelForm for ArticleGrouper that sanitizes initial M2M data."""

    class Meta:
        model = models.ArticleGrouper
        fields = '__all__'

    def get_initial_for_field(self, field, field_name):
        if field_name in self.initial:
            value = self.initial[field_name]
        else:
            value = field.initial
        if hasattr(value, 'all'):
            value = list(value.all())
        elif callable(value):
            value = value()
        if (isinstance(value, (datetime.datetime, datetime.time)) and not field.widget.supports_microseconds):
            value = value.replace(microsecond=0)
        return value


@admin.register(ArticleGrouper)
class ArticleGrouperAdmin(ExtendedGrouperVersionAdminMixin, StateIndicatorMixin, GrouperModelAdmin):
    form = ArticleGrouperAdminForm
    content_model = models.ArticleContent  # Explicitly set the content model
    list_display = [
        '__str__',
        'author',
        'app_config',
        'state_indicator',  # From StateIndicatorMixin
        'serial',
        'episode',
    ]
    list_filter = [
        'app_config',
        'author',
        'serial',
    ]
    search_fields = ['author__name', 'serial__name', 'translations__title']  # Example, assuming title on content

    def get_changeform_initial_data(self, request):
        """Preselect owner and author based on the logged in user."""
        initial = super().get_changeform_initial_data(request)
        if request.user.is_authenticated:
            initial.setdefault("owner", request.user.pk)
            try:
                person = Person.objects.get(user=request.user)
                initial.setdefault("author", person.pk)
            except Person.DoesNotExist:
                pass
        return initial

    def save_model(self, request, obj, form, change):
        """Handle many-to-many data when creating the related ArticleContent."""
        m2m_keys = [
            f"{CONTENT_PREFIX}categories",
            f"{CONTENT_PREFIX}tags",
            f"{CONTENT_PREFIX}related",
        ]
        m2m_data = {key: form.cleaned_data.pop(key, []) for key in m2m_keys if key in form.cleaned_data}

        # Extract translated fields from POST data because the autogenerated
        # grouper form does not include them. Tests submit fields using the
        # ``content__<field>_<lang>`` naming pattern.
        translated_post = {}
        for lang_code, _lang in settings.LANGUAGES:
            for field in ("title", "slug", "lead_in"):
                key = f"{CONTENT_PREFIX}{field}_{lang_code}"
                if key in request.POST:
                    translated_post.setdefault(lang_code, {})[field] = request.POST[key]

        super().save_model(request, obj, form, change)

        content_qs = self.content_model._original_manager.filter(article_grouper=obj)
        content = (
            form._content_instance if form._content_instance and form._content_instance.pk else content_qs.latest("pk")
        )

        for lang_code, values in translated_post.items():
            content.set_current_language(lang_code)
            for field, value in values.items():
                setattr(content, field, value)
            content.save()
        if f"{CONTENT_PREFIX}categories" in m2m_data:
            content.categories.set(m2m_data[f"{CONTENT_PREFIX}categories"])
        if f"{CONTENT_PREFIX}tags" in m2m_data:
            content.tags.set(m2m_data[f"{CONTENT_PREFIX}tags"])
        if f"{CONTENT_PREFIX}related" in m2m_data:
            content.related.set(m2m_data[f"{CONTENT_PREFIX}related"])


@admin.register(models.ArticleContent)
class ArticleContentAdmin(
    ExtendedVersionAdminMixin,
    AllTranslationsMixin,
    PlaceholderAdminMixin,
    FrontendEditableAdminMixin,
    TranslatableAdmin
):
    form = ArticleAdminForm
    # ExtendedVersionAdminMixin manages list display and actions

    # fieldsets define the edit view for a version (ArticleContent)
    fieldsets = (
        (None, {
            'fields': (
                # 'article_grouper',  # Should NOT be editable here; it's fixed for a version.
                #                        ExtendedVersionAdminMixin handles this link.
                'title',
                'is_featured',
                'lead_in',
                # 'content',  # PlaceholderField handled by PlaceholderAdminMixin
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
    filter_horizontal = ['categories', 'related']

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
        return models.ArticleGrouper.objects.filter(serial=obj).count()
    episodes_count.short_description = _('Total episodes')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context['serial_episodes'] = models.ArticleContent.objects.filter(
            article_grouper__serial_id=object_id
        ).order_by('article_grouper__episode')  # Order by episode on the grouper
        return self.changeform_view(request, object_id, form_url, extra_context)


# admin.site.register(models.Article, ArticleAdmin)  # Removed, ArticleContentAdmin registered with decorator
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
