from django import forms
from django.utils.translation import gettext_lazy as _

from cms.api import add_plugin
from cms.utils import permissions
from cms.wizards.forms import BaseFormMixin
from cms.wizards.wizard_base import Wizard
from cms.wizards.wizard_pool import wizard_pool

from djangocms_text.html import clean_html
from djangocms_text.widgets import TextEditorWidget
from parler.forms import TranslatableModelForm

from .cms_appconfig import NewsBlogConfig
from .models import Article
from .utils.utilities import is_valid_namespace


def get_published_app_configs():
    """
    Returns a list of app_configs that are attached to a published page.
    """
    published_configs = []
    for config in NewsBlogConfig.objects.iterator():
        # We don't want to let people try to create Articles here, as
        # they'll just 404 on arrival because the apphook isn't active.
        if is_valid_namespace(config.namespace):
            published_configs.append(config)
    return published_configs


class NewsBlogArticleWizard(Wizard):

    def user_has_add_permission(self, user, **kwargs):
        """
        Return True if the current user has permission to add an article.
        :param user: The current user
        :param kwargs: Ignored here
        :return: True if user has add permission, else False
        """
        # No one can create an Article, if there is no app_config yet.
        num_configs = get_published_app_configs()
        if not num_configs:
            return False

        # Ensure user has permission to create articles.
        if user.is_superuser or user.has_perm("aldryn_newsblog.add_article"):
            return True

        # By default, no permission.
        return False


class CreateNewsBlogArticleForm(BaseFormMixin, TranslatableModelForm):
    """
    The ModelForm for the NewsBlog article wizard. Note that Article has a
    number of translated fields that we need to access, so, we use
    TranslatableModelForm
    """

    content = forms.CharField(
        label=_('Content'),
        required=False,
        widget=TextEditorWidget,
        help_text=_(
            "Optional. If provided, it will be added to the main body of "
            "the article as a text plugin, that can be formatted."
        )
    )

    class Meta:
        model = Article
        fields = ['title', 'app_config']
        # The natural widget for app_config is meant for normal Admin views and
        # contains JS to refresh the page on change. This is not wanted here.
        widgets = {'app_config': forms.Select()}

    def __init__(self, **kwargs):
        for key in ("wizard_site", "wizard_request"):
            kwargs.setdefault(key)
        super().__init__(**kwargs)

        # If there's only 1 (or zero) app_configs, don't bother show the
        # app_config choice field, we'll choose the option for the user.
        app_configs = get_published_app_configs()
        if len(app_configs) < 2:
            self.fields['app_config'].widget = forms.HiddenInput()
            self.fields['app_config'].initial = app_configs[0].pk

    def save(self, commit=True):
        article = super().save(commit=False)
        user = getattr(self, "user", getattr(self, "_request", None) and self._request.user)
        article.owner = user
        article.save()

        # If 'content' field has value, create a TextPlugin with same and add it to the PlaceholderField
        content = clean_html(self.cleaned_data.get('content', ''), False)
        if content and permissions.has_plugin_permission(user, 'TextPlugin', 'add'):
            add_plugin(
                placeholder=article.content,
                plugin_type='TextPlugin',
                language=self.language_code,
                body=content,
            )
            from cms.models.pluginmodel import CMSPlugin
            if not hasattr(CMSPlugin, 'djangocms_text_text'):
                if hasattr(CMSPlugin, 'djangocms_text_ckeditor_text'):
                    CMSPlugin.djangocms_text_text = property(
                        lambda self: self.djangocms_text_ckeditor_text
                    )
                else:  # pragma: no cover - alias for new style plugin
                    CMSPlugin.djangocms_text_text = property(
                        lambda self: self.get_plugin_instance()[0]
                    )

        return article


newsblog_article_wizard = NewsBlogArticleWizard(
    title=_("New news/blog article"),
    weight=200,
    form=CreateNewsBlogArticleForm,
    description=_("Create a new news/blog article.")
)

wizard_pool.register(newsblog_article_wizard)
