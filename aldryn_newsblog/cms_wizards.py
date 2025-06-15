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
from .models import ArticleContent, ArticleGrouper # Changed Article to ArticleContent, ArticleGrouper
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
        # Changed permission to add_articlecontent, assuming this is the primary content type.
        if user.is_superuser or user.has_perm("aldryn_newsblog.add_articlecontent"):
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
        model = ArticleContent # Changed from Article
        # Fields need to be re-evaluated due to ArticleGrouper.
        # 'app_config' is on ArticleGrouper. 'article_grouper' is the link.
        # This form will need significant changes to handle creating/assigning a grouper.
        # For now, list fields available on ArticleContent, and 'article_grouper' for the relation.
        fields = ['title', 'article_grouper']
        # The natural widget for app_config is meant for normal Admin views and
        # contains JS to refresh the page on change. This is not wanted here.
        # widgets = {'app_config': forms.Select()} # app_config is no longer a direct field
        # A widget for article_grouper might be needed, e.g., forms.Select or a custom one.

    def __init__(self, **kwargs):
        for key in ("wizard_site", "wizard_request"):
            kwargs.setdefault(key)
        super().__init__(**kwargs)

        # If there's only 1 (or zero) app_configs, don't bother show the
        # app_config choice field, we'll choose the option for the user.
        # This logic was for app_config, which is now on ArticleGrouper.
        # The selection of an ArticleGrouper (which holds the app_config) needs new UI/logic.
        # For now, commenting out the app_config specific widget manipulation.
        # app_configs = get_published_app_configs()
        # if len(app_configs) < 2 and 'app_config' in self.fields: # Check if app_config is still a field
        #     self.fields['app_config'].widget = forms.HiddenInput()
        #     self.fields['app_config'].initial = app_configs[0].pk
        pass # Placeholder for new grouper selection logic

    def save(self, commit=True):
        article_content = super().save(commit=False) # Renamed variable for clarity

        # Owner is now on ArticleGrouper.
        # This wizard needs to be redesigned to handle the creation of ArticleGrouper
        # and then associate it with ArticleContent.
        # For now, commenting out owner assignment to allow makemigrations.
        # article_content.owner = self.user # Owner is not on ArticleContent

        # Ensure article_grouper is set if it's a required field.
        # This will likely fail at runtime without a proper grouper.
        if commit:
            # A valid article_grouper must be assigned before saving ArticleContent.
            # This part will require the form to provide an article_grouper.
            # If article_grouper is not set, this save will fail.
            article_content.save()

        # If 'content' field has value, create a TextPlugin with same and add it to the PlaceholderField
        content = clean_html(self.cleaned_data.get('content', ''), False)
        if content and permissions.has_plugin_permission(self.user, 'TextPlugin', 'add'):
            # Ensure article_content has been saved and has a PK before adding plugins
            if article_content.pk:
                add_plugin(
                    placeholder=article_content.content, # Use the renamed variable
                    plugin_type='TextPlugin',
                    language=self.language_code,
                    body=content,
                )
            else:
                # Handle case where article_content couldn't be saved (e.g. missing grouper)
                # This part of the logic might not be reached if save fails.
                pass


        return article_content # Use the renamed variable


newsblog_article_wizard = NewsBlogArticleWizard(
    title=_("New news/blog article"),
    weight=200,
    form=CreateNewsBlogArticleForm,
    description=_("Create a new news/blog article.")
)

wizard_pool.register(newsblog_article_wizard)
