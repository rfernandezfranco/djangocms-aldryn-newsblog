from datetime import timedelta

from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import override

from aldryn_newsblog.feeds import CategoryFeed, LatestArticlesFeed, TagFeed
from djangocms_versioning.models import Version

from . import NewsBlogTransactionTestCase


class TestFeeds(NewsBlogTransactionTestCase):

    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="feed_publisher")

    def test_latest_feeds(self):
        article_draft = self.create_article(title="Current Article for Feed")
        v_article = Version.objects.get_for_content(article_draft)
        v_article.publish(self.staff_user)
        v_article.created = now() - timedelta(hours=1)
        v_article.save(update_fields=['created'])

        future_article_draft = self.create_article(title="Future Article for Feed")
        v_future = Version.objects.get_for_content(future_article_draft)
        v_future.publish(self.staff_user)
        v_future.created = now() + timedelta(days=3)
        v_future.save(update_fields=['created'])

        url = reverse(
            f'{self.app_config.namespace}:article-list-feed'
        )
        self.request = self.get_request('en', url)
        self.request.current_page = self.page
        feed = LatestArticlesFeed()(self.request)

        self.assertContains(feed, article_draft.title)
        self.assertNotContains(feed, future_article_draft.title)

    def test_tag_feed(self):
        tagged_drafts_dict = self.create_tagged_articles(
            tags=('tag1', 'tag2'), title_prefix="Tagged Feed Article"
        )

        published_tagged_articles = {'tag1': [], 'tag2': []}
        for tag_slug, drafts_list in tagged_drafts_dict.items():
            for draft_content in drafts_list:
                v = Version.objects.get_for_content(draft_content)
                v.publish(self.staff_user)
                v.created = now() - timedelta(minutes=1)
                v.save(update_fields=['created'])
                published_tagged_articles[tag_slug].append(v.content) # content might be new

        url = reverse(
            f'{self.app_config.namespace}:article-list-by-tag-feed',
            args=['tag1']
        )
        self.request = self.get_request('en', url)
        self.request.current_page = self.page
        feed = TagFeed()(self.request, 'tag1')

        for article_content in published_tagged_articles['tag1']:
            self.assertContains(feed, article_content.title)
        for different_tag_article_content in published_tagged_articles['tag2']:
            self.assertNotContains(feed, different_tag_article_content.title)

    def test_category_feed(self):
        lang = self.category1.get_current_language()
        with override(lang):
            article_cat1_draft = self.create_article(title="Category 1 Feed Article")
            article_cat1_draft.categories.add(self.category1)
            v_cat1 = Version.objects.get_for_content(article_cat1_draft)
            v_cat1.publish(self.staff_user)
            v_cat1.created = now() - timedelta(minutes=1)
            v_cat1.save(update_fields=['created'])

            article_cat2_draft = self.create_article(title="Category 2 Feed Article")
            article_cat2_draft.categories.add(self.category2)
            v_cat2 = Version.objects.get_for_content(article_cat2_draft)
            v_cat2.publish(self.staff_user)
            v_cat2.created = now() - timedelta(minutes=1)
            v_cat2.save(update_fields=['created'])

            url = reverse(
                f'{self.app_config.namespace}:article-list-by-category-feed',
                args=[self.category1.slug]
            )
            self.request = self.get_request(lang, url)
            self.request.current_page = self.page

            feed = CategoryFeed()(self.request, self.category1.slug)

            self.assertContains(feed, article_cat1_draft.title)
            self.assertNotContains(feed, article_cat2_draft.title)
