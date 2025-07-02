from aldryn_newsblog.cms_wizards import CreateNewsBlogArticleForm
from aldryn_newsblog.models import ArticleGrouper
from aldryn_newsblog.tests import NewsBlogTestCase


class CreateNewsBlogArticleFormTestCase(NewsBlogTestCase):

    def get_form(self, has_content, has_permission):
        data = {'title': 'My super title', 'app_config': self.app_config.id}
        # Create a temporary ArticleGrouper for the wizard form. The grouper is
        # normally handled by the admin and not exposed in the wizard, but our
        # refactored models require it. Using a fresh grouper per form keeps the
        # test logic close to the original intent while satisfying the new
        # validation requirements.
        grouper = ArticleGrouper.objects.create(app_config=self.app_config, owner=self.create_user(), author=self.create_person())
        data['article_grouper'] = grouper.pk
        if has_content:
            data['content'] = 'My super content'

        form = CreateNewsBlogArticleForm(wizard_language='en', data=data)
        form.user = self.create_user(is_staff=has_permission, is_superuser=has_permission)
        self.assertTrue(form.is_valid())
        return form

    def test_article_is_saved_with_content_user_with_plugin_permission(self):
        form = self.get_form(has_content=True, has_permission=True)

        article = form.save()
        self.assertTrue(article.__class__._original_manager.filter(id=article.id).exists())
        self.assertEqual(article.content.get_plugins('en').count(), 1)
        plugin = article.content.get_plugins('en').get()
        self.assertEqual(plugin.plugin_type, 'TextPlugin')
        self.assertEqual(plugin.djangocms_text_text.body, 'My super content')

    def test_article_is_saved_without_content_with_plugin_permission(self):
        form = self.get_form(has_content=False, has_permission=True)

        article = form.save()
        self.assertTrue(article.__class__._original_manager.filter(id=article.id).exists())
        self.assertFalse(article.content.get_plugins('en').exists())

    def test_article_is_saved_with_content_without_plugin_permission(self):
        form = self.get_form(has_content=True, has_permission=False)

        article = form.save()
        self.assertTrue(article.__class__._original_manager.filter(id=article.id).exists())
        self.assertFalse(article.content.get_plugins('en').exists())

    def test_article_is_saved_without_content_without_plugin_permission(self):
        form = self.get_form(has_content=False, has_permission=False)

        article = form.save()
        self.assertTrue(article.__class__._original_manager.filter(id=article.id).exists())
        self.assertFalse(article.content.get_plugins('en').exists())
