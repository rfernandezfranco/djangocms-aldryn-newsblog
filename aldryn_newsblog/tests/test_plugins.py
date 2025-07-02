import datetime
import time

from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.translation import override

from cms import api
from djangocms_versioning.models import Version

from aldryn_newsblog.models import NewsBlogConfig

from . import NewsBlogTestCase


class TestAppConfigPluginsBase(NewsBlogTestCase):
    plugin_to_test = 'TextPlugin'
    plugin_params = {}

    def setUp(self):
        super().setUp()
        self.placeholder = self.plugin_page.get_admin_content(self.language).get_placeholders().first()
        api.add_plugin(
            self.placeholder, self.plugin_to_test, self.language,
            app_config=self.app_config, **self.plugin_params)
        self.plugin = self.placeholder.get_plugins()[0].get_plugin_instance()[0]
        self.plugin.save()
        # self.plugin_page.publish(self.language)
        self.publish_page(self.plugin_page, self.language, self.user)
        self.another_app_config = NewsBlogConfig.objects.create(
            namespace=self.rand_str())


class TestPluginLanguageHelperMixin:

    def _test_plugin_languages_with_article(self, article):
        """Set up conditions to test plugin languages edge cases"""
        # Add 'de' translation to one of the articles
        title_de = 'title-de'
        title_en = article.title
        article.set_current_language('de')
        article.title = title_de
        article.save()

        # Unpublish page with newsblog apphook
        # self.page.unpublish('en')
        # cache.clear()
        response = self.client.get(self.plugin_page.get_absolute_url())

        # This article should not be visible on 'en' page/plugin

        # In CMS 3.11, there was originally `assertNotContains` because the django.urls.reverese function in the
        # .utils.is_valid_namespace function only returned the selected language version.
        # This is no longer the case in CMS 4.1.
        self.assertContains(response, title_en)


class TestArchivePlugin(TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogArchivePlugin'

    def test_archive_plugin(self):
        dates = [
            datetime.datetime(2014, 11, 15, 12, 0, 0, 0, datetime.timezone.utc),
            datetime.datetime(2014, 11, 16, 12, 0, 0, 0, datetime.timezone.utc),
            datetime.datetime(2015, 1, 15, 12, 0, 0, 0, datetime.timezone.utc),
            datetime.datetime(2015, 1, 15, 12, 0, 0, 0, datetime.timezone.utc),
            datetime.datetime(2015, 1, 15, 12, 0, 0, 0, datetime.timezone.utc),
            datetime.datetime(2015, 2, 15, 12, 0, 0, 0, datetime.timezone.utc),
        ]
        articles = []
        for d in dates:
            article = self.create_article()
            version = Version.objects.get_for_content(article)
            version.publish(self.user)
            version.created = d
            version.save(update_fields=['created'])
            articles.append(article)
        response = self.client.get(self.plugin_page.get_absolute_url())
        response_content = force_str(response.content)
        needle = '<a href="/page/{year}/{month}/"[^>]*>'
        '[^<]*<span class="badge">{num}</span>'
        month1 = needle.format(year=2014, month=11, num=2)
        month2 = needle.format(year=2015, month=2, num=1)
        month3 = needle.format(year=2015, month=1, num=3)
        self.assertRegex(response_content, month1)
        self.assertRegex(response_content, month2)
        self.assertRegex(response_content, month3)


class TestArticleSearchPlugin(TestAppConfigPluginsBase):
    """Simply tests that the plugin form renders on the page."""
    # This is a really weak test. To do more, we'll have to submit the form,
    # yadda yadda yadda. Test_views.py should already test the other side of
    # this.
    plugin_to_test = 'NewsBlogArticleSearchPlugin'
    plugin_params = {
        "max_articles": 5,
    }

    def test_article_search_plugin(self):
        needle = '<input type="hidden" name="max_articles" value="{num}">'
        response = self.client.get(self.plugin_page.get_absolute_url())
        self.assertContains(response, needle.format(num=5))
        search_url = reverse(f'{self.app_config.namespace}:article-search')
        self.assertContains(response, f'action="{search_url}"')


class TestAuthorsPlugin(TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogAuthorsPlugin'

    def test_authors_plugin(self):
        author1, author2 = self.create_person(), self.create_person()
        # Published, author1 articles in our current namespace
        author1_articles = []
        for _ in range(3):
            article = self.create_article(author=author1, is_published=True)
            author1_articles.append(article)

        # Published, author2 articles in our current namespace
        other_articles = []
        for _ in range(5):
            article = self.create_article(author=author2, is_published=True)
            other_articles.append(article)

        # Unpublished, author1 articles in our current namespace
        for _ in range(7):
            article = self.create_article(
                author=author1,
                is_published=False
            )
            other_articles.append(article)

        # Published, author1 articles in a different namespace
        other_articles.append(self.create_article(
            author=author1,
            app_config=self.another_app_config,
            is_published=True,
        ))

        # REQUIRED DUE TO USE OF RAW QUERIES
        time.sleep(1)

        response = self.client.get(self.plugin_page.get_absolute_url())
        response_content = force_str(response.content)
        # This pattern tries to accommodate all the templates from all the
        # versions of this package.
        pattern = r'(?s)<a href="{url}">.*?</a>'  # noqa: #W605
        author1_pattern = pattern.format(
            url=reverse(
                f'{self.app_config.namespace}:article-list-by-author',
                args=[author1.slug]
            )
        )
        author2_pattern = pattern.format(
            url=reverse(
                f'{self.app_config.namespace}:article-list-by-author',
                args=[author2.slug]
            )
        )
        self.assertRegex(response_content, author1_pattern)
        self.assertRegex(response_content, author2_pattern)


class TestCategoriesPlugin(TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogCategoriesPlugin'

    def test_categories_plugin(self):
        # Published, category1 articles in our current namespace
        cat1_articles = []
        for _ in range(3):
            article = self.create_article(is_published=True)
            article.categories.add(self.category1)
            cat1_articles.append(article)

        # Published category2 articles in our namespace
        other_articles = []
        for _ in range(5):
            article = self.create_article(is_published=True)
            article.categories.add(self.category2)
            other_articles.append(article)

        # Some tag1, but unpublished articles
        for _ in range(7):
            article = self.create_article(is_published=False)
            article.categories.add(self.category1)
            other_articles.append(article)

        # Some tag1 articles in another namespace
        for _ in range(1):
            article = self.create_article(app_config=self.another_app_config, is_published=True)
            article.categories.add(self.category1)
            other_articles.append(article)

        # REQUIRED DUE TO USE OF RAW QUERIES
        time.sleep(1)

        response = self.client.get(self.plugin_page.get_absolute_url())
        response_content = force_str(response.content)
        # We use two different patterns in alternation because different
        # versions of newsblog have different templates
        pattern = r'<span[^>]*>{num}</span>\s*<a href=[^>]*>{name}</a>'  # noqa: #W605
        pattern += r'|<a href=[^>]*>{name}</a>\s*<span[^>]*>{num}</span>'  # noqa: #W605
        needle1 = pattern.format(num=3, name=self.category1.name)
        needle2 = pattern.format(num=5, name=self.category2.name)
        self.assertRegex(response_content, needle1)
        self.assertRegex(response_content, needle2)

        # Categories should be ordered by article count descending
        index_cat2 = response_content.index(self.category2.name)
        index_cat1 = response_content.index(self.category1.name)
        self.assertLess(index_cat2, index_cat1)


class TestFeaturedArticlesPlugin(TestPluginLanguageHelperMixin,
                                 TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogFeaturedArticlesPlugin'
    plugin_params = {
        "article_count": 5,
    }

    def test_featured_articles_plugin(self):
        featured_articles = [self.create_article(
            is_featured=True,
            is_published=True
        ) for _ in range(3)]
        # Some featured articles but unpublished articles
        other_articles = [self.create_article(
            is_featured=True,
            is_published=False
        ) for _ in range(3)]
        # Some non-featured articles in the same namespace
        other_articles += [self.create_article(is_published=True) for _ in range(3)]
        # Some featured articles in another namespace
        other_articles += [self.create_article(
            is_featured=True,
            app_config=self.another_app_config,
            is_published=True,
        ) for _ in range(3)]

        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in featured_articles:
            self.assertContains(response, article.title)
        for article in other_articles:
            self.assertNotContains(response, article.title)

    def test_featured_articles_plugin_unpublished_app_page(self):
        with override(self.language):
            articles = [
                self.create_article(is_featured=True, is_published=True)
                for _ in range(3)
            ]

        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in articles:
            self.assertContains(response, article.title)

        # self.page.unpublish(self.language)
        # self.reload_urls()
        # cache.clear()
        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in articles:
            # In CMS 3.11, there was originally `assertNotContains` because the django.urls.reverese function in the
            # .utils.is_valid_namespace function only returned the selected language version.
            # This is no longer the case in CMS 4.1.
            self.assertContains(response, article.title)

    def test_featured_articles_plugin_language(self):
        article = self.create_article(is_featured=True, is_published=True)
        self._test_plugin_languages_with_article(article)


class TestLatestArticlesPlugin(TestPluginLanguageHelperMixin,
                               TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogLatestArticlesPlugin'
    plugin_params = {
        "latest_articles": 7,
    }

    def test_latest_articles_plugin(self):
        articles = [self.create_article(is_published=True) for _ in range(7)]
        another_app_config = NewsBlogConfig.objects.create(namespace='another')
        another_articles = [self.create_article(app_config=another_app_config, is_published=True)
                            for _ in range(3)]
        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in articles:
            self.assertContains(response, article.title)
        for article in another_articles:
            self.assertNotContains(response, article.title)

    def _test_latest_articles_plugin_exclude_count(self, exclude_count=0):
        self.plugin.exclude_featured = exclude_count
        self.plugin.save()
        # self.plugin_page.publish(self.plugin.language)
        articles = []
        featured_articles = []
        for idx in range(7):
            if idx % 2:
                featured_articles.append(self.create_article(is_featured=True, is_published=True))
            else:
                articles.append(self.create_article(is_published=True))
        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in articles:
            self.assertContains(response, article.title)
        # check that configured among of featured articles is excluded
        for featured_article in featured_articles[:exclude_count]:
            self.assertNotContains(response, featured_article.title)
        # ensure that other articles featured articles are present
        for featured_article in featured_articles[exclude_count:]:
            self.assertContains(response, featured_article.title)

    def test_latest_articles_plugin_exclude_featured(self):
        self._test_latest_articles_plugin_exclude_count(3)

    def test_latest_articles_plugin_no_excluded_featured(self):
        self._test_latest_articles_plugin_exclude_count()

    def test_latest_articles_plugin_unpublished_app_page(self):
        with override(self.language):
            articles = [self.create_article(is_published=True) for _ in range(3)]

        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in articles:
            self.assertContains(response, article.title)

        # self.page.unpublish(self.language)
        # self.reload_urls()
        # cache.clear()
        response = self.client.get(self.plugin_page.get_absolute_url())
        for article in articles:
            # In CMS 3.11, there was originally `assertNotContains` because the django.urls.reverese function in the
            # .utils.is_valid_namespace function only returned the selected language version.
            # This is no longer the case in CMS 4.1.
            self.assertContains(response, article.title)

    def test_latest_articles_plugin_language(self):
        article = self.create_article(is_published=True)
        self._test_plugin_languages_with_article(article)


class TestPrefixedLatestArticlesPlugin(TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogLatestArticlesPlugin'
    plugin_params = {
        "latest_articles": 7,
    }

    def setUp(self):
        super().setUp()
        self.app_config.template_prefix = 'dummy'
        self.app_config.save()

    def test_latest_articles_plugin(self):
        response = self.client.get(self.plugin_page.get_absolute_url())
        self.assertContains(response, 'This is dummy latest articles plugin')


class TestRelatedArticlesPlugin(TestPluginLanguageHelperMixin,
                                NewsBlogTestCase):

    def test_related_articles_plugin(self):
        main_article = self.create_article(app_config=self.app_config, is_published=True)
        alias_content = self.create_alias_content("newsblog_social", self.language)
        version = alias_content.versions.last()
        version.publish(self.user)

        placeholder = alias_content.get_placeholders()[0]
        api.add_plugin(placeholder, 'NewsBlogRelatedPlugin', self.language)

        plugin = placeholder.get_plugins()[0].get_plugin_instance()[0]
        plugin.save()

        # self.plugin_page.publish(self.language)

        main_article.save()
        for _ in range(3):
            a = self.create_article(is_published=True)
            a.save()
            main_article.related.add(a.article_grouper)

        another_language_articles = []
        with override('de'):
            for _ in range(4):
                a = self.create_article(is_published=True)
                main_article.related.add(a.article_grouper)
                another_language_articles.append(a)

        self.assertEqual(main_article.related.count(), 7)
        unrelated = []
        for _ in range(5):
            unrelated.append(self.create_article(is_published=True))

        response = self.client.get(main_article.get_absolute_url())
        for grouper in main_article.related.all():
            content = grouper.articlecontent_set.language(self.language).first()
            if content:
                self.assertContains(response, content.title)
        for article in unrelated:
            self.assertNotContains(response, article.title)

        # self.page.unpublish('de')
        # self.reload_urls()
        # cache.clear()
        version.unpublish(self.user)

        response = self.client.get(main_article.get_absolute_url())
        for article in another_language_articles:
            self.assertNotContains(response, article.title)

    def test_latest_articles_plugin_language(self):
        main_article, related_article = (
            self.create_article(is_published=True) for _ in range(2))
        main_article.related.add(related_article.article_grouper)
        response_main = self.client.get(main_article.get_absolute_url())
        response_related = self.client.get(related_article.get_absolute_url())
        self.assertContains(response_main, main_article.title)
        self.assertContains(response_related, related_article.title)


class TestTagsPlugin(TestAppConfigPluginsBase):
    plugin_to_test = 'NewsBlogTagsPlugin'

    def test_tags_plugin(self):
        # Published, tag1-tagged articles in our current namespace
        self.create_tagged_articles(3, tags=['tag1'], is_published=True)['tag1']
        other_articles = self.create_tagged_articles(5, tags=['tag2'], is_published=True)['tag2']
        # Some tag1, but unpublished articles
        other_articles += self.create_tagged_articles(
            7, tags=['tag1'], is_published=False)['tag1']
        # Some tag1 articles in another namespace
        other_articles += self.create_tagged_articles(
            1, tags=['tag1'], app_config=self.another_app_config, is_published=True)['tag1']

        # REQUIRED DUE TO USE OF RAW QUERIES
        time.sleep(1)

        response = self.client.get(self.plugin_page.get_absolute_url())
        response_content = force_str(response.content)
        self.assertRegex(response_content, r'tag1\s*<span[^>]*>3</span>')  # noqa: #W605
        self.assertRegex(response_content, r'tag2\s*<span[^>]*>5</span>')  # noqa: #W605
