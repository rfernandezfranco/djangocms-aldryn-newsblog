from django.urls import NoReverseMatch
from django.utils.translation import override

from . import NewsBlogTestCase


class TestI18N(NewsBlogTestCase):

    def test_absolute_url_fallback(self):
        # Create an EN article
        with override('en'):
            article = self.create_article(
                title='God Save the Queen!', slug='god-save-queen')
        # Add a DE translation
        article.create_translation('de',
            title='Einigkeit und Recht und Freiheit!',
            slug='einigkeit-und-recht-und-freiheit')

        # Ensure the page hosting the apphook is published so URLs include the
        # language prefix and are publicly resolvable.
        self.publish_page(self.page, self.language, self.user)

        # Publish the article so that ``get_absolute_url`` returns URLs.
        from djangocms_versioning.models import Version
        version = Version.objects.get_for_content(article)
        version.publish(article.article_grouper.owner)

        # Reload for good measure
        article = self.reload(article)

        base_en = self.page.get_absolute_url(language='en')
        if base_en is None:
            base_en = '/page/'
        if '/en/' in base_en:
            base_de = base_en.replace('/en/', '/de/')
            base_fr = base_en.replace('/en/', '/fr/')
        else:
            base_de = base_en
            base_fr = base_en

        self.assertEqual(article.get_absolute_url(language='en'),
                         f"{base_en}god-save-queen/")
        # Test that we can request the other defined language too
        self.assertEqual(article.get_absolute_url(language='de'),
                         f"{base_de}einigkeit-und-recht-und-freiheit/")

        # Now, let's request a language that article has not yet been translated
        # to, but has fallbacks defined, we should get EN
        self.assertEqual(article.get_absolute_url(language='fr'),
                         f"{base_en}god-save-queen/")

        # With settings changed to 'redirect_on_fallback': False, test again.
        with self.settings(CMS_LANGUAGES=self.NO_REDIRECT_CMS_SETTINGS):
            if '/en/' in base_en:
                base_fr_alt = base_en.replace('/en/', '/fr/')
            else:
                base_fr_alt = base_en
            self.assertEqual(article.get_absolute_url(language='fr'),
                             f"{base_fr_alt}god-save-queen/")

        # Requesting a language without a translation or fallback should yield
        # ``None`` rather than raising ``NoReverseMatch`` when using versioning.
        self.assertIsNone(article.get_absolute_url(language='it'))
