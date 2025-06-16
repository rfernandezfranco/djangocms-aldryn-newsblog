from django.core.management import call_command
from django.utils.translation import activate

from aldryn_newsblog.models import ArticleContent
from djangocms_versioning.models import Version

from . import NewsBlogTestCase


class TestCommands(NewsBlogTestCase):

    def test_rebuild_search_data_command(self):
        activate(self.language)
        article_content_draft = self.create_article(title="Command Test Article Search Data")

        if not hasattr(self, 'staff_user'):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="cmd_test_publisher")

        version = Version.objects.get_for_content(article_content_draft)
        # Changed to use instance method
        version.publish(self.staff_user)
        article_content_published = version.content # content object might be replaced

        expected_search_data = article_content_published.get_search_data(language=self.language)

        translation_obj = article_content_published.translations.get(language_code=self.language)
        translation_obj.search_data = ''
        translation_obj.save(update_fields=['search_data'])

        fresh_article_content = ArticleContent.objects.language(self.language).get(pk=article_content_published.pk)
        self.assertEqual(fresh_article_content.safe_get_translation(self.language).search_data, '', "Search data should be empty before command run.")

        call_command('rebuild_article_search_data', languages=[self.language])

        fresh_article_content.refresh_from_db()
        updated_translation = fresh_article_content.translations.get(language_code=self.language)
        self.assertEqual(updated_translation.search_data, expected_search_data,
                         "Search data was not rebuilt correctly by the command.")
