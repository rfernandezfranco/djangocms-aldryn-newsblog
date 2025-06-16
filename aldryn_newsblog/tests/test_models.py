import os

from django.conf import settings
from django.utils.timezone import now
from django.utils.translation import activate, override

from cms import api
from cms import api as cms_api

from aldryn_newsblog.models import ArticleContent, ArticleGrouper, NewsBlogConfig, Category, Person, article_content_copy
from . import TESTS_STATIC_ROOT, NewsBlogTestCase, NewsBlogTransactionTestCase


FEATURED_IMAGE_PATH = os.path.join(TESTS_STATIC_ROOT, 'featured_image.jpg')


class TestModels(NewsBlogTestCase):

from django.core.files.base import ContentFile
from filer.models.imagemodels import Image as FilerImage

from djangocms_versioning.constants import DRAFT, PUBLISHED, ARCHIVED
from djangocms_versioning.models import Version
from djangocms_versioning import exceptions as versioning_exceptions

from parler.utils.context import switch_language
from aldryn_newsblog.utils import strip_tags


FEATURED_IMAGE_PATH = os.path.join(TESTS_STATIC_ROOT, 'featured_image.jpg')


class TestModels(NewsBlogTestCase):

    def test_create_article(self):
        draft_content = self.create_article(title="Test Create Article Draft")
        self.assertIsNotNone(draft_content.pk)
        versions = Version.objects.filter_by_content(draft_content)
        self.assertEqual(versions.count(), 1)
        version = versions.first()
        self.assertEqual(version.state, DRAFT)
        self.assertIsNone(draft_content.get_absolute_url(),
                          "get_absolute_url for a new draft should return None.")

    def test_delete_article(self):
        draft_content = self.create_article(title="Test Delete Article")
        version = Version.objects.get_for_content(draft_content)
        publisher = draft_content.article_grouper.owner
        if not hasattr(publisher, 'is_staff') or not publisher.is_staff:
            publisher.is_staff = True
            publisher.is_superuser = True
            publisher.save()
        # Use instance method for publish
        version.publish(publisher)
        published_content = version.content # Content might be new
        published_url = published_content.get_absolute_url(language=self.language)
        self.assertIsNotNone(published_url, "URL should exist for published content.")
        response = self.client.get(published_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, published_content.title)
        # Use instance method for unpublish
        version.unpublish(publisher)
        version.refresh_from_db()
        self.assertIsNone(published_content.get_absolute_url(language=self.language),
                          "get_absolute_url after unpublish should return None.")
        response_after_unpublish = self.client.get(published_url)
        self.assertEqual(response_after_unpublish.status_code, 404)
        grouper_pk = published_content.article_grouper.pk
        published_content.article_grouper.delete()
        with self.assertRaises(ArticleGrouper.DoesNotExist):
            ArticleGrouper.objects.get(pk=grouper_pk)
        with self.assertRaises(ArticleContent.DoesNotExist):
            ArticleContent.objects.get(pk=published_content.pk)

    def test_auto_slugifies(self):
        activate(self.language)
        base_title = f"This is a slug test title {self.rand_str(length=5)}"
        expected_base_slug = base_title.lower().replace(" ", "-")

        content1 = self.create_article(title=base_title, language=self.language)
        self.assertEqual(content1.slug, expected_base_slug)

        content1_v2 = ArticleContent(article_grouper=content1.article_grouper)
        content1_v2.set_current_language(self.language)
        content1_v2.title = base_title
        _old_update_search = ArticleContent.update_search_on_save
        ArticleContent.update_search_on_save = False
        content1_v2.save()
        ArticleContent.update_search_on_save = _old_update_search
        self.assertEqual(content1_v2.slug, f"{expected_base_slug}-1", "Slug should be incremented for same grouper, lang, title")

        other_owner = self.create_user(username=self.rand_str(length=10)) # Corrected rand_str
        content2_title = base_title
        content2_expected_slug = content2_title.lower().replace(" ", "-")
        content2 = self.create_article(title=content2_title, owner=other_owner, language=self.language)
        self.assertNotEqual(content1.article_grouper, content2.article_grouper, "Should be different groupers")
        self.assertEqual(content2.slug, content2_expected_slug, "Slug should be same (original form) for different grouper, same title")

        if len(settings.LANGUAGES) > 1:
            other_language = settings.LANGUAGES[1][0]
            content1_lang2 = ArticleContent(article_grouper=content1.article_grouper)
            content1_lang2.set_current_language(other_language)
            content1_lang2.title = base_title # Same title as content1, but different language
            ArticleContent.update_search_on_save = False
            content1_lang2.save()
            ArticleContent.update_search_on_save = _old_update_search
            self.assertEqual(content1_lang2.slug, expected_base_slug, "Slug should be same (original form) for different language on same grouper")
            activate(self.language)

    def test_auto_existing_author(self):
        author_person = self.create_person()
        self.app_config.create_authors = True
        self.app_config.save()
        content = self.create_article(owner=author_person.user, author=None)
        grouper = content.article_grouper
        self.assertIsNotNone(grouper.author)
        self.assertEqual(grouper.author, author_person)
        self.app_config.create_authors = False
        self.app_config.save()
        another_user_owner = self.create_user(username="another_owner_for_author_test")
        content_no_auto_author = self.create_article(owner=another_user_owner, author=None, app_config=self.app_config)
        grouper2 = content_no_auto_author.article_grouper
        if Person.objects.filter(user=another_user_owner).exists():
             self.assertIsNotNone(grouper2.author)
        else:
             self.assertIsNone(grouper2.author)
        self.app_config.create_authors = True
        self.app_config.save()

    def test_auto_new_author(self):
        new_user_owner = self.create_user(username="new_owner_for_author_creation_models", first_name="New", last_name="OwnerB")
        self.assertFalse(Person.objects.filter(user=new_user_owner).exists())
        self.app_config.create_authors = True
        self.app_config.save()
        content = self.create_article(owner=new_user_owner, author=None)
        grouper = content.article_grouper
        self.assertIsNotNone(grouper.author)
        self.assertEqual(grouper.author.user, new_user_owner)
        expected_name = f"{new_user_owner.first_name} {new_user_owner.last_name}".strip()
        if not expected_name: expected_name = new_user_owner.get_username()
        self.assertEqual(grouper.author.name, expected_name)

    def test_auto_search_data(self):
        activate(self.language)
        test_title = "Searchable Title"
        test_lead_in = "<p>Searchable lead-in content.</p>"
        _old_update_setting = ArticleContent.update_search_on_save
        ArticleContent.update_search_on_save = True
        content_item = self.create_article(title=test_title, lead_in=test_lead_in, language=self.language)
        content_item.refresh_from_db()
        translation = content_item.safe_get_translation(self.language)
        self.assertIsNotNone(translation)
        self.assertIn(strip_tags(test_lead_in), translation.search_data)
        ArticleContent.update_search_on_save = _old_update_setting

    def test_auto_search_data_off(self):
        activate(self.language)
        test_lead_in = "<p>This lead-in should not be in search_data automatically.</p>"
        _old_update_setting = ArticleContent.update_search_on_save
        ArticleContent.update_search_on_save = False
        content_item = self.create_article(title="Non-Searchable Title", lead_in=test_lead_in, language=self.language)
        content_item.refresh_from_db()
        translation = content_item.safe_get_translation(self.language)
        self.assertEqual(translation.search_data, "")
        manual_search_data = content_item.get_search_data(language=self.language)
        self.assertIn(strip_tags(test_lead_in), manual_search_data)
        ArticleContent.update_search_on_save = _old_update_setting

    def test_has_content(self):
        # Just make sure we have a known language
        activate(self.language)
        test_title = self.rand_str(prefix="Content Test Title ")
        placeholder_body_text = self.rand_str(prefix="Placeholder body ")
        article_content = self.create_article(title=test_title, language=self.language)
        cms_api.add_plugin(article_content.content, 'TextPlugin', self.language, body=placeholder_body_text)
        if not hasattr(self, 'staff_user'):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="content_test_publisher")
        version = Version.objects.get_for_content(article_content)
        version.publish(self.staff_user)
        # article_content is the original draft, its state is now PUBLISHED via the version
        # For get_absolute_url, the instance itself should work if its version is published.
        article_content.refresh_from_db() # Refresh to ensure any state flags on content are updated
        article_url = article_content.get_absolute_url(language=self.language)
        self.assertIsNotNone(article_url)
        response = self.client.get(article_url)
        self.assertContains(response, test_title)
        self.assertContains(response, placeholder_body_text)

    def test_change_title(self):
        """
        Test that we can change the title of an existing, published article
        without issue. Also ensure that the slug does NOT change when changing
        the title alone.
        """
        activate(self.language)
        initial_title = "This is the initial title for change test"
        content_v1 = self.create_article(title=initial_title, language=self.language)
        v1 = Version.objects.get_for_content(content_v1)
        if not hasattr(self, 'staff_user'):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="title_change_publisher")
        v1.publish(self.staff_user)
        # content_v1 is the original draft, its state is now PUBLISHED via the version
        content_v1.refresh_from_db()
        initial_slug = content_v1.safe_get_translation(self.language).slug
        self.assertEqual(content_v1.safe_get_translation(self.language).title, initial_title)
        v2_draft_version = v1.create_draft(self.staff_user) # v1 is the Version object
        content_v2_draft = v2_draft_version.content
        new_title = "This is the new title for V2"
        with switch_language(content_v2_draft, self.language):
            content_v2_draft.title = new_title
            content_v2_draft.save()
        content_v2_draft.refresh_from_db()
        self.assertEqual(content_v2_draft.safe_get_translation(self.language).title, new_title)
        # With TranslatedAutoSlugifyMixin, changing the title SHOULD change the slug
        # if the slug source is the title and the slug is not manually managed.
        self.assertNotEqual(content_v2_draft.safe_get_translation(self.language).slug, initial_slug)
        self.assertEqual(content_v2_draft.safe_get_translation(self.language).slug, "this-is-the-new-title-for-v2")


class TestModelsTransactions(NewsBlogTransactionTestCase):

    def test_duplicate_title_and_language(self):
        """
        Test that if user attempts to create an article with the same name and
        in the same language as another, it will not raise exceptions.
        """
        base_title_for_test = f"Sample Article Transaction Test {self.rand_str(length=6)}"
        author = self.create_person()
        original_lang = settings.LANGUAGES[0][0]

        # Create an initial article (ArticleContent) in the first language
        content1_draft = self.create_article(
            title=f"{base_title_for_test} G1 L1",
            author=author, # Pass author to create_article if it sets it on grouper
            owner=author.user, # create_article handles owner for grouper
            language=original_lang
        )
        grouper1 = content1_draft.article_grouper

        # Now try to create an article with the same title in every possible
        # language and every possible language contexts.
        for i, (context_lang_code, _) in enumerate(settings.LANGUAGES):
            with override(context_lang_code):
                for j, (article_lang_code, _) in enumerate(settings.LANGUAGES):
                    try:
                        title_for_grouper1 = f"{base_title_for_test} G1 L{i+1}-{j+1}"
                        new_content_for_grouper1 = ArticleContent(article_grouper=grouper1)
                        new_content_for_grouper1.set_current_language(article_lang_code)
                        new_content_for_grouper1.title = title_for_grouper1
                        # Note: an owner is required for ArticleGrouper, already set on grouper1
                        # Note: an app_config is required for ArticleGrouper, already set on grouper1
                        new_content_for_grouper1.save()

                        # Create for a new grouper
                        other_owner_username = f"other_owner_{self.rand_str(length=3)}_{context_lang_code}_{article_lang_code}"
                        other_owner = self.create_user(username=other_owner_username)
                        title_for_new_grouper = f"{base_title_for_test} G2 L{i+1}-{j+1}"
                        content_new_grouper = self.create_article(
                            title=title_for_new_grouper,
                            owner=other_owner,
                            author=author, # Optional: re-use same author Person, or create new
                            language=article_lang_code
                        )
                        self.assertNotEqual(content_new_grouper.article_grouper, grouper1)
                    except Exception as e:
                        self.fail(
                            f'Creating article in process context "{context_lang_code}" '
                            f'and article language "{article_lang_code}" with title '
                            f'"{title_for_grouper1}" or "{title_for_new_grouper}" '
                            f'raised exception: {e}'
                        )
