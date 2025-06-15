from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.utils.translation import get_language_from_request
from django.utils.translation import gettext as _
from django.utils.translation import override

from cms.toolbar_base import CMSToolbar
from cms.toolbar_pool import toolbar_pool

from aldryn_apphooks_config.utils import get_app_instance
from aldryn_translation_tools.utils import (
    get_admin_url, get_object_from_request,
)

from .cms_appconfig import NewsBlogConfig
from .models import ArticleContent, ArticleGrouper # Changed Article


@toolbar_pool.register
class NewsBlogToolbar(CMSToolbar):
    # watch_models must be a list, not a tuple
    # see https://github.com/divio/django-cms/issues/4135
    watch_models = [ArticleContent, ArticleGrouper, ] # Changed Article
    supported_apps = ('aldryn_newsblog',)

    def get_on_delete_redirect_url(self, article_content, language): # Renamed article to article_content
        # app_config is now on article_grouper
        # FIXME #VERSIONING: Ensure article_content has article_grouper and app_config loaded
        if article_content and hasattr(article_content, 'article_grouper') and article_content.article_grouper:
            with override(language):
                url = reverse(
                    f'{article_content.article_grouper.app_config.namespace}:article-list')
            return url
        return None # Fallback or raise error

    def __get_newsblog_config(self):
        try:
            __, config = get_app_instance(self.request)
            if not isinstance(config, NewsBlogConfig):
                # This is not the app_hook you are looking for.
                return None
        except ImproperlyConfigured:
            # There is no app_hook at all.
            return None

        return config

    def populate(self):
        config = self.__get_newsblog_config()
        if not config:
            # Do nothing if there is no NewsBlog app_config to work with
            return

        user = getattr(self.request, 'user', None)
        try:
            view_name = self.request.resolver_match.view_name
        except AttributeError:
            view_name = None

        if user and view_name:
            language = get_language_from_request(self.request, check_path=True)

            # If we're on an Article detail page, then get the article_content
            if view_name == f'{config.namespace}:article-detail':
                article_content = get_object_from_request(ArticleContent, self.request) # Changed Article
            else:
                article_content = None

            menu = self.toolbar.get_or_create_menu('newsblog-app',
                                                   config.get_app_title())

            change_config_perm = user.has_perm(
                'aldryn_newsblog.change_newsblogconfig')
            add_config_perm = user.has_perm(
                'aldryn_newsblog.add_newsblogconfig')
            config_perms = [change_config_perm, add_config_perm]

            # Permissions should now refer to ArticleContent or ArticleGrouper
            # Assuming ArticleContent for content-related operations.
            change_article_perm = user.has_perm(
                'aldryn_newsblog.change_articlecontent') # Changed article to articlecontent
            delete_article_perm = user.has_perm(
                'aldryn_newsblog.delete_articlecontent') # Changed article to articlecontent
            add_article_perm = user.has_perm('aldryn_newsblog.add_articlecontent') # Changed article to articlecontent
            article_perms = [change_article_perm, add_article_perm,
                             delete_article_perm, ]

            if change_config_perm:
                url_args = {}
                if language:
                    url_args = {'language': language, }
                url = get_admin_url('aldryn_newsblog_newsblogconfig_change',
                                    [config.pk, ], **url_args)
                menu.add_modal_item(_('Configure addon'), url=url)

            if any(config_perms) and any(article_perms):
                menu.add_break()

            if change_article_perm:
                url_args = {}
                if config:
                    # The changelist should probably filter by app_config on the grouper
                    url_args = {'article_grouper__app_config__id__exact': config.pk}
                url = get_admin_url('aldryn_newsblog_articlecontent_changelist', # Changed
                                    **url_args)
                menu.add_sideframe_item(_('Article list'), url=url)

            if add_article_perm:
                # Adding an article now means creating ArticleContent, which needs an ArticleGrouper.
                # The admin 'add' view for ArticleContent might need pre-selected grouper or allow creation.
                # For now, assuming 'app_config' might be used to pre-fill grouper selection if that form supports it.
                # 'owner' is on grouper.
                url_args = {} # Removed: 'app_config': config.pk, 'owner': user.pk
                if language:
                    url_args.update({'language': language, })
                # FIXME: The 'add' view for ArticleContent will need to handle grouper creation/selection.
                # This URL might need to point to an intermediate step or a more complex form.
                url = get_admin_url('aldryn_newsblog_articlecontent_add', **url_args) # Changed
                menu.add_modal_item(_('Add new article'), url=url)

            if change_article_perm and article_content: # Changed article to article_content
                url_args = {}
                if language:
                    url_args = {'language': language, }
                url = get_admin_url('aldryn_newsblog_articlecontent_change', # Changed
                                    [article_content.pk, ], **url_args)
                menu.add_modal_item(_('Edit this article'), url=url,
                                    active=True)

            if delete_article_perm and article_content: # Changed article to article_content
                redirect_url = self.get_on_delete_redirect_url(
                    article_content, language=language)
                url = get_admin_url('aldryn_newsblog_articlecontent_delete', # Changed
                                    [article_content.pk, ])
                menu.add_modal_item(_('Delete this article'), url=url,
                                    on_close=redirect_url)
