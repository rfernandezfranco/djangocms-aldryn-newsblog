from aldryn_newsblog.models import ArticleContent, ArticleGrouper
from djangocms_versioning.models import Version
from djangocms_versioning.constants import PUBLISHED, DRAFT, ARCHIVED
from django.utils.timezone import now
from django.contrib.contenttypes.models import ContentType


from . import NewsBlogTestCase


class TestManagers(NewsBlogTestCase):

    def test_published_articles_filtering_and_retrieval(self):
        if not hasattr(self, 'staff_user'):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="manager_test_publisher")

        published_articles_content = []
        draft_articles_content = []

        for i in range(5):
            ac = self.create_article(title=f"Test Article {i}")
            if i < 3:
                version = Version.objects.get_for_content(ac)
                version.publish(self.staff_user)
                published_articles_content.append(version.content) # content might be new
            else:
                draft_articles_content.append(ac)

        content_type = ContentType.objects.get_for_model(ArticleContent)
        published_versions = Version.objects.filter(
            content_type=content_type,
            state=PUBLISHED,
            published__lte=now()
        )
        published_pks = published_versions.values_list('object_id', flat=True)

        retrieved_published_articles = ArticleContent._base_manager.filter(pk__in=published_pks)

        self.assertEqual(retrieved_published_articles.count(), 3)
        for pac in published_articles_content:
            self.assertIn(pac, retrieved_published_articles)

        for dac in draft_articles_content:
            self.assertNotIn(dac, retrieved_published_articles)

    def test_view_article_not_published(self):
        draft_article_content = self.create_article(title="Draft Article URL Test")

        self.assertIsNone(draft_article_content.get_absolute_url(),
                          "get_absolute_url for a draft article should return None.")

        if not hasattr(self, 'staff_user'):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="manager_url_test_publisher")

        ac_to_unpublish = self.create_article(title="Article to Unpublish URL Test")
        version = Version.objects.get_for_content(ac_to_unpublish)
        version.publish(self.staff_user)
        # ac_to_unpublish remains the original instance, but its state is now published via the version

        self.assertIsNotNone(ac_to_unpublish.get_absolute_url(), "Published article should have a URL.")

        version.unpublish(self.staff_user)
        version.refresh_from_db()
        # ac_to_unpublish's version is now unpublished.

        self.assertIsNone(ac_to_unpublish.get_absolute_url(),
                          "get_absolute_url for an unpublished (archived) article should return None.")
