from django.contrib.sites.shortcuts import get_current_site
from django.utils.translation import override

from aldryn_newsblog.sitemaps import NewsBlogSitemap
from djangocms_versioning.models import Version

from . import NewsBlogTestCase


class TestSitemaps(NewsBlogTestCase):

    def _sitemap_urls(self, sitemap):
        urls_info = sitemap.get_urls()
        urls = [url_info['location'] for url_info in urls_info]
        return urls

    def _article_urls(self, articles, lang):
        self.request = self.get_request(lang)
        host = 'https://' + get_current_site(self.request).domain
        urls = []
        for article in articles:
            url = article.get_absolute_url(lang)
            if url:
                urls.append(host + url)
        return urls

    def assertArticlesIn(self, articles, sitemap):
        urls = self._sitemap_urls(sitemap)
        article_urls = self._article_urls(articles, sitemap.language)

        for url in article_urls:
            self.assertIn(url, urls)

    def assertArticlesNotIn(self, articles, sitemap):
        urls = self._sitemap_urls(sitemap)
        article_urls = self._article_urls(articles, sitemap.language)

        for url in article_urls:
            self.assertNotIn(url, urls)

    def assertSitemapLanguage(self, sitemap, lang):
        self.request = self.get_request(lang)
        urls = self._sitemap_urls(sitemap)
        host = 'https://' + get_current_site(self.request).domain
        base = self.page.get_absolute_url(language=lang)
        if base is None:
            base = '/page/'
        if f'/{lang}/' in base:
            url_start = host + base.split(f'/{lang}/')[0] + f'/{lang}/'
        else:
            url_start = host + base

        for url in urls:
            self.assertTrue(url.startswith(url_start))

    def test_listening_all_instances(self):
        self.publish_page(self.root_page, self.language, self.user)
        self.publish_page(self.page, self.language, self.user)
        unpublished_article = self.create_article(is_published=False)
        articles = [self.create_article(is_published=True) for _ in range(10)]
        sitemap = NewsBlogSitemap()
        self.assertArticlesIn(articles, sitemap)
        self.assertArticlesNotIn([unpublished_article], sitemap)

    def test_listening_namespace(self):
        self.publish_page(self.root_page, self.language, self.user)
        self.publish_page(self.page, self.language, self.user)
        unpublished_article = self.create_article(is_published=False)
        articles = [self.create_article(is_published=True) for _ in range(10)]
        sitemap = NewsBlogSitemap(namespace=self.app_config.namespace)
        self.assertArticlesIn(articles, sitemap)
        self.assertArticlesNotIn([unpublished_article], sitemap)

    def test_listening_unexisting_namespace(self):
        self.publish_page(self.root_page, self.language, self.user)
        self.publish_page(self.page, self.language, self.user)
        unpublished_article = self.create_article(is_published=False)
        articles = [self.create_article(is_published=True) for _ in range(10)]
        sitemap = NewsBlogSitemap(namespace='not exists')
        self.assertFalse(sitemap.items())
        self.assertArticlesNotIn([unpublished_article] + articles, sitemap)

    def test_languages_support(self):
        self.publish_page(self.root_page, self.language, self.user)
        self.publish_page(self.page, self.language, self.user)
        with override('en'):
            multilanguage_article = self.create_article()
            en_article = self.create_article()

        multilanguage_article.create_translation(
            'de', title='DE title', slug='de-article')
        with override('de'):
            de_article = self.create_article(language='de')

        for article in (multilanguage_article, en_article, de_article):
            version = Version.objects.get_for_content(article)
            version.publish(article.article_grouper.owner)

        en_sitemap = NewsBlogSitemap(language='en')
        self.assertArticlesIn([multilanguage_article, en_article], en_sitemap)
        self.assertArticlesNotIn([de_article], en_sitemap)
        self.assertSitemapLanguage(en_sitemap, 'en')

        de_sitemap = NewsBlogSitemap(language='de')
        self.assertArticlesIn([multilanguage_article, de_article], de_sitemap)
        self.assertArticlesNotIn([en_article], de_sitemap)
        self.assertSitemapLanguage(de_sitemap, 'de')
