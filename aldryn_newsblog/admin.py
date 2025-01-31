from typing import Optional

from django import forms
from django.contrib import admin
from django.urls.exceptions import NoReverseMatch
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse_lazy
from django.utils import translation
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from cms.admin.placeholderadmin import FrontendEditableAdminMixin
from cms.api import add_plugin
from cms.toolbar.utils import get_object_preview_url
from cms.utils.i18n import get_current_language
from cms.utils.urlutils import static_with_version

from aldryn_apphooks_config.admin import BaseAppHookConfig, ModelAppHookConfig
from aldryn_people.models import Person
from aldryn_translation_tools.admin import AllTranslationsMixin
from parler.admin import TranslatableAdmin
from parler.forms import TranslatableModelForm

from djangocms_text_ckeditor.cms_plugins import TextPlugin
from redirects.models import Redirect
try:
    from awesome_slugify import Slugify
except ModuleNotFoundError:
    from slugify import Slugify
unicodeSlugify = Slugify(translate=None)

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
    oldSlug = forms.CharField(
        label=_('slug'),
        required=False, max_length=255, 
        help_text=_(
            'Used in the URL. If changed, the URL will change. '
            'Clear it to have it re-created automatically.'),
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = models.Article
        fields = [
            'app_config',
            'categories',
            'featured_image',
            'is_featured',
            'is_published',
            'lead_in',
            'meta_description',
            'meta_keywords',
            'meta_title',
            'owner',
            'related',
            'slug',
            'tags',
            'title',
            'serial',
            'episode',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        qs = models.Article.objects
        if self.instance.app_config_id:
            qs = models.Article.objects.filter(
                app_config=self.instance.app_config)
        elif 'initial' in kwargs and 'app_config' in kwargs['initial']:
            qs = models.Article.objects.filter(
                app_config=kwargs['initial']['app_config'])

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if 'related' in self.fields:
            self.fields['related'].queryset = qs

        # Don't allow app_configs to be added here. The correct way to add an
        # apphook-config is to create an apphook on a cms Page.
        self.fields['app_config'].widget.can_add_related = False
        # Don't allow related articles to be added here.
        # doesn't makes much sense to add articles from another article other
        # than save and add another.
        if ('related' in self.fields and  # noqa: W504
                hasattr(self.fields['related'], 'widget')):
            self.fields['related'].widget.can_add_related = False


class ArticleAdmin(
    AllTranslationsMixin,
    FrontendEditableAdminMixin,
    ModelAppHookConfig,
    TranslatableAdmin
):
    form = ArticleAdminForm
    list_display = ('title', 'preview', 'app_config', 'slug', 'is_featured',
                    'is_published')
    list_filter = [
        'app_config',
        'categories',
    ]
    actions = (
        make_featured, make_not_featured,
        make_published, make_unpublished,
    )
    fieldsets = (
        (None, {
            'fields': (
                'title',
                'author',
                'publishing_date',
                'is_published',
                'is_featured',
                'featured_image',
                'lead_in',
            )
        }),
        (_('Serial Options'), {
            'classes': ('collapse',),
            'fields': (
                'serial',
                'episode',
            )
        }),
        (_('Meta Options'), {
            'classes': ('collapse',),
            'fields': (
                'slug',
                'oldslug',
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
                'owner',
                'app_config',
            )
        }),
    )
    filter_horizontal = [
        'categories',
    ]
    app_config_values = {
        'default_published': 'is_published'
    }
    app_config_selection_title = ''
    app_config_selection_desc = ''

    class Media:
        js = (
            static_with_version("cms/js/dist/bundle.admin.base.min.js"),
            static_with_version("cms/js/dist/bundle.admin.pagetree.min.js"),
        )
        css = {
            "all": (static_with_version("cms/css/cms.base.css"), static_with_version("cms/css/cms.pagetree.css"))
        }
    # Reference from site-packages\cms\templates\admin\cms\page\tree\menu.html
    @admin.display(description="Preview")
    def preview(self, obj):
        language = get_current_language()
        url = get_object_preview_url(obj, language=language)
        tooltip = _("View on site")
        return format_html(
            f'''
            <div class="cms-tree-item cms-tree-item-preview">
                <div class="cms-tree-item-inner cms-hover-tooltip cms-hover-tooltip-left cms-hover-tooltip-delay" 
                    data-cms-tooltip="{tooltip}">
                    <a class="js-cms-pagetree-page-view cms-icon-view" href="{url}" target="_top" "="">
                        <span class="sr-only" style="visibility: hidden">{tooltip}</span>
                    </a>
                </div>
            </div>
            '''
        )

    def add_view(self, request, *args, **kwargs):
        data = request.GET.copy()
        try:
            person = Person.objects.get(user=request.user)
            data['author'] = person.pk
            request.GET = data
        except Person.DoesNotExist:
            pass

        data['owner'] = request.user.pk
        request.GET = data
        return super().add_view(request, *args, **kwargs)

    def get_deleted_objects(self, objs, request) -> tuple:
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        # This is bad and I should feel bad. (by django-cms official)
        if 'placeholder' in perms_needed:
            perms_needed.remove('placeholder')
        return deleted_objects, model_count, perms_needed, protected
    def response_add(self, request, obj, post_url_continue=None):
        l = translation.get_language()
        textPlugin = add_plugin(
            obj.content, TextPlugin, l, body=_("double click here to edit article content")
        )
        slug = request.POST.get('slug')
        if slug:
            obj.slug = unicodeSlugify(slug)
        else:
            obj.slug = unicodeSlugify(obj.title)
        obj.save()
        
        return super(ArticleAdmin, self).response_add(request, obj, post_url_continue=None)
   
    def get_form(self, request, obj=None, **kwargs):
        form = super(ArticleAdmin, self).get_form(request, obj, **kwargs)
        if obj:
            form.base_fields['oldSlug'].initial = obj.slug
        else:
            form.base_fields['oldSlug'].initial = ''
        return form
    def response_change(self, request, obj):
        slug = request.POST.get('slug')
        if slug:
            obj.slug = unicodeSlugify(slug)
        else:
            obj.slug = unicodeSlugify(obj.title)
        obj.save()
        oldslug = request.POST.get('oldSlug')
        if oldslug != obj.slug:
            site = get_current_site(request)
            # Only need to add when using django.contrib.redirects in INSTALLED_APPS, not django-redirect
            # from urllib.parse import urlparse
            #
            # domain = request.headers.get('Origin')
            # domain = urlparse(domain).netloc if domain else site
            #
            # Create a new site when site was not set in settings.py
            # if site.domain != domain:
            #     site, _ = Site.objects.get_or_create(
            #         domain=domain,
            #         name=domain,
            #     )
            oldUrl = reverse_lazy(f'{obj.app_config.namespace}:article-detail', kwargs={'slug': oldslug, })
            newUrl = reverse_lazy(f'{obj.app_config.namespace}:article-detail', kwargs={'slug': obj.slug, })
            Redirect.objects.get_or_create(
                site=site,
                old_path=oldUrl,
                new_path=newUrl,
            )
            aaa = Redirect.objects.all()
        return super(ArticleAdmin, self).response_change(request, obj)

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
        return models.Article.objects.filter(serial=obj).count()
    episodes_count.short_description = _('Total episodes')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context['serial_episodes'] = models.Article.objects.filter(serial_id=object_id).order_by('episode')
        return self.changeform_view(request, object_id, form_url, extra_context)


admin.site.register(models.Article, ArticleAdmin)
admin.site.register(models.Serial, SerialAdmin)


class NewsBlogConfigAdmin(
    AllTranslationsMixin,
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
