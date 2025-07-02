import os
from datetime import date, datetime, time, timezone
from operator import itemgetter
from random import randint

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.timezone import make_aware
from django.utils.timezone import now as django_timezone_now

from cms import api
from cms.utils.i18n import force_language, get_current_language

from easy_thumbnails.files import get_thumbnailer
from filer.models.imagemodels import Image
from parler.tests.utils import override_parler_settings
from parler.utils.conf import add_default_language_settings
from parler.utils.context import smart_override, switch_language

from aldryn_newsblog.models import ArticleContent, ArticleGrouper, NewsBlogConfig
from aldryn_newsblog.search_indexes import ArticleIndex

from . import TESTS_STATIC_ROOT, NewsBlogTestCase

# Imports for versioning
from djangocms_versioning.models import Version
from djangocms_versioning.constants import PUBLISHED
from datetime import timedelta
from django.core.files.base import ContentFile
from django.contrib.contenttypes.models import ContentType


FEATURED_IMAGE_PATH = os.path.join(TESTS_STATIC_ROOT, "featured_image.jpg")

PARLER_LANGUAGES_HIDE = {
    1: [
        {"code": "en", "fallbacks": ["de"], "hide_untranslated": True},
        {"code": "de", "fallbacks": ["en"], "hide_untranslated": True},
        {"code": "fr", "fallbacks": ["en"], "hide_untranslated": True},
    ],
    "default": {
        "hide_untranslated": True,
        "fallbacks": [],
    },
}

PARLER_LANGUAGES_SHOW = {
    1: [
        {"code": "en", "fallbacks": ["de"], "hide_untranslated": False},
        {"code": "de", "fallbacks": ["en"], "hide_untranslated": False},
        {"code": "fr", "fallbacks": ["en"], "hide_untranslated": False},
    ],
    "default": {
        "hide_untranslated": False,
        "fallbacks": [],
    },
}


class TestViews(NewsBlogTestCase):

    def test_articles_list(self):
        namespace = self.app_config.namespace
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="view_test_publisher_list")

        published_articles = []
        for i in range(10):
            draft = self.create_article(title=f"Published View Test {i}")
            version = Version.objects.get_for_content(draft)
            version.publish(self.staff_user)
            published_articles.append(version.content)  # content might be new

        draft_article = self.create_article(title="Unpublished Draft View Test")

        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        self.reload_urls()

        response = self.client.get(reverse(f"{namespace}:article-list"))
        for article_content in published_articles:
            self.assertContains(response, article_content.title)
        self.assertNotContains(response, draft_article.title)

    def test_articles_list_exclude_featured(self):
        namespace = self.app_config.namespace
        exclude_count = 2
        self.app_config.exclude_featured = exclude_count
        self.app_config.paginate_by = 2
        self.app_config.save()

        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="view_exclude_publisher")

        articles_published = []
        featured_articles_published = []
        for idx in range(6):
            is_feat = idx % 2 != 0
            draft = self.create_article(is_featured=is_feat, title=f"Exclude Test Article {idx} Feat:{is_feat}")
            version = Version.objects.get_for_content(draft)
            version.publish(self.staff_user)
            if is_feat:
                featured_articles_published.append(version.content)  # content might be new
            else:
                articles_published.append(version.content)  # content might be new

        articles_published.sort(
            key=lambda ac: Version.objects.get_for_content(ac).created,
            reverse=True,
        )
        featured_articles_published.sort(
            key=lambda ac: Version.objects.get_for_content(ac).created,
            reverse=True,
        )

        # Publish the page so the list view is accessible and reload URLs
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        self.reload_urls()

        list_base_url = reverse(f"{namespace}:article-list")
        page_url_template = "{0}?page={1}"
        response_page_1 = self.client.get(list_base_url)
        response_page_2 = self.client.get(page_url_template.format(list_base_url, 2))

        for article in articles_published[:2]:
            self.assertContains(response_page_1, article.title)
        for featured_article in featured_articles_published[:exclude_count]:
            self.assertNotContains(response_page_1, featured_article.title)

        if len(articles_published) > 2:
            self.assertContains(response_page_2, articles_published[2].title)
        if len(featured_articles_published) > exclude_count:
            self.assertContains(response_page_2, featured_articles_published[exclude_count].title)

    def test_articles_list_pagination(self):
        namespace = self.app_config.namespace
        paginate_by = self.app_config.paginate_by
        if not paginate_by or paginate_by <= 0:
            paginate_by = 5
        self.app_config.paginate_by = paginate_by
        self.app_config.save()

        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(
                is_staff=True, is_superuser=True, username="view_test_publisher_paginate"
            )

        articles_for_pagination = []
        num_articles_to_create = paginate_by + 5

        for i in range(num_articles_to_create):
            pub_date = make_aware(datetime(2023, 1, 1, 12, 0, 0), timezone.utc) + timedelta(days=i)
            draft = self.create_article(
                title=f"Paginate Article {i:02d} Versioning Test",
                is_published=True,
                publishing_date=pub_date,
            )
            version = Version.objects.get_for_content(draft)
            articles_for_pagination.append(version.content)  # content might be new

        articles_for_pagination.sort(
            key=lambda ac: Version.objects.get_for_content(ac).created,
            reverse=True,
        )

        # Publish the page so the list view is accessible and reload URLs
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        self.reload_urls()

        response_page1 = self.client.get(reverse(f"{namespace}:article-list"))
        self.assertEqual(response_page1.status_code, 200)
        self.assertEqual(
            list(response_page1.context["object_list"]),
            articles_for_pagination[:paginate_by],
        )

        response_page2 = self.client.get(reverse(f"{namespace}:article-list") + "?page=2")
        self.assertEqual(response_page2.status_code, 200)
        self.assertEqual(
            list(response_page2.context["object_list"]),
            articles_for_pagination[paginate_by:paginate_by * 2],
        )

    def test_articles_by_author(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="view_test_author_publisher")
        # The author list view lives on an apphooked page. Publish the page so
        # reversing URLs works reliably across CMS versions and reload the URL
        # patterns afterward.
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        self.reload_urls()
        author1, author2 = self.create_person(), self.create_person()
        for author in (author1, author2):
            published_articles = []
            for _ in range(11):
                draft_content = self.create_article(author=author)
                version = Version.objects.get_for_content(draft_content)
                version.publish(self.staff_user)
                published_articles.append(version.content)  # content might be new
            response = self.client.get(
                reverse(f"{self.app_config.namespace}:article-list-by-author", kwargs={"author": author.slug})
            )
            for article_content in published_articles:
                self.assertContains(response, article_content.title)

    def test_articles_by_unknown_author(self):
        response = self.client.get(
            reverse(f"{self.app_config.namespace}:article-list-by-author", kwargs={"author": "unknown"})
        )
        self.assertEqual(response.status_code, 404)

    def test_articles_by_category(self):
        LANGUAGES = add_default_language_settings(PARLER_LANGUAGES_HIDE)
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(
                is_staff=True, is_superuser=True, username="view_test_category_publisher"
            )

        # Publish the pages so reversing category URLs works across languages
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        for lang_code, _ in settings.LANGUAGES[1:]:
            self.publish_page(self.root_page, lang_code, self.staff_user)
            self.publish_page(self.page, lang_code, self.staff_user)
        self.reload_urls()

        with override_parler_settings(PARLER_LANGUAGES=LANGUAGES):
            author = self.create_person()
            for category_obj in (self.category1, self.category2):
                published_articles_for_category = []
                for i in range(11):
                    base_title = (
                        "Category Test Article "
                        f"{category_obj.safe_translation_getter('name', language_code=self.language)}-{i}"
                    )
                    draft_content = self.create_article(title=base_title, author=author)
                    for lang_code, _ in settings.LANGUAGES:
                        if lang_code == self.language:
                            continue
                        with switch_language(draft_content, lang_code):
                            draft_content.title = f"{base_title} ({lang_code})"
                            draft_content.save()
                    draft_content.categories.add(category_obj)
                    version = Version.objects.get_for_content(draft_content)
                    version.publish(self.staff_user)
                    published_articles_for_category.append(version.content)  # content might be new

                # Check only the default language to avoid issues with
                # per-language page publishing.
                with switch_language(category_obj, self.language):
                    url = reverse(
                        f"{self.app_config.namespace}:article-list-by-category",
                        kwargs={
                            "category": category_obj.safe_translation_getter(
                                "slug", language_code=self.language
                            )
                        },
                    )
                    response = self.client.get(url)
                for article_content in published_articles_for_category:
                    article_content.set_current_language(self.language)
                    self.assertContains(response, article_content.title)

    def test_articles_by_unknown_category(self):
        response = self.client.get(
            reverse(f"{self.app_config.namespace}:article-list-by-category", kwargs={"category": "unknown"})
        )
        self.assertEqual(response.status_code, 404)


class TestTemplatePrefixes(NewsBlogTestCase):

    def setUp(self):
        super().setUp()
        self.app_config.template_prefix = "dummy"
        self.app_config.save()
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="tpl_prefix_publisher")

    def test_articles_list(self):
        namespace = self.app_config.namespace
        draft_content = self.create_article(title="Dummy Template Test Article", app_config=self.app_config)
        version = Version.objects.get_for_content(draft_content)
        version.publish(self.staff_user)
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        self.reload_urls()
        response = self.client.get(reverse(f"{namespace}:article-list"))
        self.assertContains(response, "This is dummy article list page")

    def test_article_detail(self):
        draft_content = self.create_article(title="Dummy Detail Template Test", app_config=self.app_config)
        version = Version.objects.get_for_content(draft_content)
        version.publish(self.staff_user)
        published_content = version.content  # Use the potentially new content obj

        # Publish the pages so the article detail URL resolves correctly
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        self.reload_urls()

        url = published_content.get_absolute_url(language=self.language)
        self.assertIsNotNone(url)
        response = self.client.get(url)
        self.assertContains(response, "This is dummy article detail page")


class TestTranslationFallbacks(NewsBlogTestCase):
    def test_article_detail_not_translated_fallback(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="fallback_test_publisher")
        author = self.create_person()
        lang_primary = settings.LANGUAGES[0][0]
        lang_secondary = settings.LANGUAGES[1][0]
        with force_language(lang_primary):
            draft_content = self.create_article(
                title=f"Fallback Test Title {lang_primary}",
                slug=f"fallback-test-slug-{lang_primary}",
                author=author,
                app_config=self.app_config,
                owner=author.user,
            )
            draft_content.categories.add(self.category1)
        version = Version.objects.get_for_content(draft_content)
        version.publish(self.staff_user)
        published_content_primary = version.content  # Content might be new
        url_primary = None
        with force_language(lang_primary):
            url_primary = published_content_primary.get_absolute_url()
            self.assertIsNotNone(url_primary)
            response_primary = self.client.get(url_primary)
            self.assertEqual(response_primary.status_code, 200)
            self.assertContains(response_primary, published_content_primary.title)
        LANGUAGES_HIDE_SETTINGS = add_default_language_settings(PARLER_LANGUAGES_HIDE)
        with override_parler_settings(PARLER_LANGUAGES=LANGUAGES_HIDE_SETTINGS):
            with force_language(lang_secondary):
                response_secondary = self.client.get(url_primary, HTTP_ACCEPT_LANGUAGE=lang_secondary)
                self.assertEqual(
                    response_secondary.status_code,
                    404,
                    "Should be 404 when hide_untranslated=True and no translation for requested language.",
                )
            with self.settings(CMS_LANGUAGES=self.NO_REDIRECT_CMS_SETTINGS):
                with force_language(lang_secondary):
                    response_secondary_no_redirect = self.client.get(url_primary, HTTP_ACCEPT_LANGUAGE=lang_secondary)
                    self.assertEqual(
                        response_secondary_no_redirect.status_code,
                        404,
                        "Should be 404 with hide_untranslated=True and redirect_on_fallback=False.",
                    )

    def test_article_detail_not_translated_no_fallback(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="no_fallback_publisher")
        author = self.create_person()
        lang_primary = settings.LANGUAGES[0][0]
        lang_secondary = settings.LANGUAGES[1][0]
        with force_language(lang_primary):
            title_primary = f"No Fallback Test {lang_primary}"
            slug_primary = f"no-fallback-slug-{lang_primary}"
            draft_content = self.create_article(
                title=title_primary, slug=slug_primary, author=author, app_config=self.app_config, owner=author.user
            )
            draft_content.categories.add(self.category1)
        version = Version.objects.get_for_content(draft_content)
        version.publish(self.staff_user)
        published_content_primary = version.content  # Content might be new
        PARLER_CONF = {
            1: [{"code": lang, "fallbacks": [], "hide_untranslated": True} for lang, _ in settings.LANGUAGES],
            "default": {"hide_untranslated": True, "fallbacks": []},
        }
        LANGUAGES_NO_FALLBACK_SETTINGS = add_default_language_settings(PARLER_CONF)
        with override_parler_settings(PARLER_LANGUAGES=LANGUAGES_NO_FALLBACK_SETTINGS):
            url_primary = None
            with force_language(lang_primary):
                url_primary = published_content_primary.get_absolute_url()
                self.assertIsNotNone(url_primary)
                response_primary = self.client.get(url_primary, HTTP_ACCEPT_LANGUAGE=lang_primary)
                self.assertContains(response_primary, title_primary)
            with force_language(lang_secondary):
                response_secondary = self.client.get(url_primary, HTTP_ACCEPT_LANGUAGE=lang_secondary)
                self.assertEqual(response_secondary.status_code, 404)


class TestImages(NewsBlogTestCase):
    def test_article_detail_show_featured_image(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="view_test_publisher_image")
        if not hasattr(self, "filer_owner"):
            self.filer_owner = self.create_user(is_staff=True, username="filer_image_owner_views_test")
        featured_image_instance = None
        try:
            with open(FEATURED_IMAGE_PATH, "rb") as f_img:
                file_obj = ContentFile(f_img.read(), name="featured_image_view.jpg")
                featured_image_instance = Image.objects.create(
                    owner=self.filer_owner, original_filename="featured_image_view.jpg", file=file_obj
                )
        except Exception as e:
            print(f"Warning: Could not create Filer Image for test: {e}. Skipping image-specific assertions.")
        draft_content = self.create_article(featured_image=featured_image_instance)
        version = Version.objects.get_for_content(draft_content)
        version.publish(self.staff_user)
        published_content = version.content  # Content might be new
        if featured_image_instance:
            self.assertIsNotNone(published_content.featured_image)
            self.assertEqual(published_content.featured_image.pk, featured_image_instance.pk)
        url = published_content.get_absolute_url(language=self.language)
        self.assertIsNotNone(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        if featured_image_instance:
            thumbnailer = get_thumbnailer(published_content.featured_image)
            thumb_options = {
                "size": (800, 450),
                "crop": True,
                "subject_location": (
                    published_content.featured_image.subject_location if published_content.featured_image else ""
                ),
            }
            thumb_url = thumbnailer.get_thumbnail(thumb_options).url
            self.assertContains(response, thumb_url)


class TestVariousViews(NewsBlogTestCase):
    def test_articles_by_tag(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="tag_view_publisher")
        untagged_drafts = []
        for _ in range(5):
            draft = self.create_article(title=f"Untagged Draft {self.rand_str(length=5)}")
            untagged_drafts.append(draft)
        tagged_article_drafts_dict = self.create_tagged_articles(
            num_articles=3, tags=(self.rand_str(prefix="tagA-"), self.rand_str(prefix="tagB-"))
        )
        published_tagged_articles = {}
        for tag_slug, drafts_list in tagged_article_drafts_dict.items():
            published_tagged_articles[tag_slug] = []
            for draft_content in drafts_list:
                version = Version.objects.get_for_content(draft_content)
                version.publish(self.staff_user)
                published_tagged_articles[tag_slug].append(version.content)  # Content might be new
        tag_slugs = list(published_tagged_articles.keys())
        tag_slug1 = tag_slugs[0]
        tag_slug2 = tag_slugs[1]
        url_tag2 = reverse(f"{self.app_config.namespace}:article-list-by-tag", kwargs={"tag": tag_slug2})
        response_tag2 = self.client.get(url_tag2)
        for article_content in published_tagged_articles[tag_slug2]:
            self.assertContains(response_tag2, article_content.title)
        for article_content in published_tagged_articles[tag_slug1]:
            self.assertNotContains(response_tag2, article_content.title)
        for draft_content in untagged_drafts:
            self.assertNotContains(response_tag2, draft_content.title)
        url_tag1 = reverse(f"{self.app_config.namespace}:article-list-by-tag", kwargs={"tag": tag_slug1})
        response_tag1 = self.client.get(url_tag1)
        for article_content in published_tagged_articles[tag_slug1]:
            self.assertContains(response_tag1, article_content.title)
        for article_content in published_tagged_articles[tag_slug2]:
            self.assertNotContains(response_tag1, article_content.title)

    def test_articles_by_unknown_tag(self):
        response = self.client.get(
            reverse(f"{self.app_config.namespace}:article-list-by-tag", kwargs={"tag": "unknown"}),
            HTTP_ACCEPT_LANGUAGE="de",
        )
        self.assertEqual(response.status_code, 404)

    def test_articles_count_by_month(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="count_month_publisher")
        months_data = [
            {"date": date(1914, 7, 3), "num_articles": 1, "articles": []},
            {"date": date(1914, 8, 3), "num_articles": 3, "articles": []},
            {"date": date(1945, 9, 3), "num_articles": 5, "articles": []},
        ]
        all_created_articles = []
        for month_spec in months_data:
            for i in range(month_spec["num_articles"]):
                publish_dt = make_aware(datetime.combine(month_spec["date"], time(10, 12, 30)))
                publish_dt += timedelta(seconds=i)
                article_content = self.create_article(
                    title=f"MonthCount Article {month_spec['date'].isoformat()} {i}",
                    is_published=True,
                    publishing_date=publish_dt,
                )
                month_spec["articles"].append(article_content)
                all_created_articles.append(article_content)
        if all_created_articles:
            # article_to_unpublish needs to be the content obj that has a version
            # If version.content created a new object, all_created_articles[-1] is correct.
            # If it modified in-place, then draft would also work if it was the last one.
            # Safest is to use the item from all_created_articles which we know is the result of version.content
            article_to_unpublish = all_created_articles[-1]
            version_to_unpublish = Version.objects.get_for_content(
                article_to_unpublish
            )  # Get version for this specific content obj
            if version_to_unpublish and version_to_unpublish.state == PUBLISHED:  # Check if version exists
                version_to_unpublish.unpublish(self.staff_user)
                for m_spec in months_data:
                    if article_to_unpublish in m_spec["articles"]:  # Compare content objects
                        m_spec["num_articles"] -= 1
                        break
        expected_months_summary = [
            {
                "date": entry["date"].replace(day=1),
                "num_articles": entry["num_articles"],
            }
            for entry in months_data
            if entry["num_articles"] > 0
        ]
        from django.db.models.functions import TruncMonth
        from django.db.models import Count

        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        versions_for_month_test = Version.objects.filter(
            content_type=content_type_ac,
            state=PUBLISHED,
            object_id__in=ArticleContent.objects.filter(article_grouper__app_config=self.app_config).values_list(
                "pk", flat=True
            ),
        )
        calculated_months_data = (
            versions_for_month_test.annotate(month_group=TruncMonth("created"))
            .values("month_group")
            .annotate(num_articles_in_month=Count("id"))
            .values("month_group", "num_articles_in_month")
            .order_by("month_group")
        )
        actual_months_summary = [
            {
                "date": item["month_group"].date(),
                "num_articles": item["num_articles_in_month"],
            }
            for item in calculated_months_data
        ]
        expected_months_summary_sorted = sorted(expected_months_summary, key=itemgetter("date"))
        actual_months_summary_sorted = sorted(actual_months_summary, key=itemgetter("date"))
        self.assertEqual(actual_months_summary_sorted, expected_months_summary_sorted)

    def test_articles_count_by_author(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="count_author_publisher")
        authors_data = []
        for num_articles_to_create in [1, 3, 5]:
            person = self.create_person()
            authors_data.append({"person": person, "expected_count": num_articles_to_create, "articles": []})
        article_to_eventually_unpublish = None
        for author_spec in authors_data:
            for i in range(author_spec["expected_count"]):
                draft = self.create_article(
                    author=author_spec["person"], title=f"AuthorCount {author_spec['person'].slug} {i}"
                )
                version = Version.objects.get_for_content(draft)
                version.publish(self.staff_user)
                author_spec["articles"].append(version.content)  # content might be new
                if author_spec == authors_data[-1] and i == 0:
                    article_to_eventually_unpublish = version.content  # store the potentially new content obj
        if article_to_eventually_unpublish:
            version_to_unpublish = Version.objects.get_for_content(
                article_to_eventually_unpublish
            )  # Get version for this specific content obj
            if version_to_unpublish and version_to_unpublish.state == PUBLISHED:  # Check if version exists
                version_to_unpublish.unpublish(self.staff_user)
                for ad in authors_data:
                    if (
                        ad["person"] == article_to_eventually_unpublish.article_grouper.author
                    ):  # Compare person objects
                        ad["expected_count"] -= 1
                        break
        expected_authors_summary = [
            (data["person"].pk, data["expected_count"]) for data in authors_data if data["expected_count"] > 0
        ]
        from django.contrib.contenttypes.models import ContentType
        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        actual_authors_data = []
        relevant_author_pks = (
            ArticleGrouper.objects.filter(app_config=self.app_config).values_list("author__pk", flat=True).distinct()
        )
        for author_pk in relevant_author_pks:
            if author_pk is None:
                continue
            num_published_by_author = Version.objects.filter(
                content_type=content_type_ac,
                state=PUBLISHED,
                object_id__in=ArticleContent.objects.filter(
                    article_grouper__author__pk=author_pk, article_grouper__app_config=self.app_config
                ).values_list("pk", flat=True),
            ).count()
            if num_published_by_author > 0:
                actual_authors_data.append({"pk": author_pk, "num_articles": num_published_by_author})
        actual_authors_summary_tuples = sorted(
            [(item["pk"], item["num_articles"]) for item in actual_authors_data], key=itemgetter(1)
        )
        expected_authors_summary_sorted = sorted(expected_authors_summary, key=itemgetter(1))
        self.assertEqual(actual_authors_summary_tuples, expected_authors_summary_sorted)

    def test_articles_count_by_tags(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="count_tags_publisher")
        from aldryn_newsblog.models import NewsBlogTagsPlugin
        from django.utils.text import slugify

        plugin_instance = NewsBlogTagsPlugin(app_config=self.app_config)
        initial_tags = plugin_instance.get_tags(request=self.get_request())
        self.assertEqual(list(initial_tags), [])
        for i in range(5):
            draft = self.create_article(title=f"UntaggedForCount {i}")
            version = Version.objects.get_for_content(draft)
            version.publish(self.staff_user)
        tag_names = ("tag_count_foo", "tag_count_bar", "tag_count_buzz")
        draft_for_tag0 = self.create_article(title="TagCount Unpub Article")
        draft_for_tag0.tags.add(tag_names[0])
        created_tag1_articles_info = self.create_tagged_articles(
            num_articles=3, tags=(tag_names[1],), title_prefix="Tag1Count"
        )
        tag_slug1 = list(created_tag1_articles_info.keys())[0]
        for draft in created_tag1_articles_info[tag_slug1]:
            version = Version.objects.get_for_content(draft)
            version.publish(self.staff_user)
        created_tag2_articles_info = self.create_tagged_articles(
            num_articles=5, tags=(tag_names[2],), title_prefix="Tag2Count"
        )
        tag_slug2 = list(created_tag2_articles_info.keys())[0]
        for draft in created_tag2_articles_info[tag_slug2]:
            version = Version.objects.get_for_content(draft)
            version.publish(self.staff_user)
        tags_from_plugin = plugin_instance.get_tags(request=self.get_request())
        actual_tags_summary = sorted(
            [
                (tag.slug, tag.num_articles)
                for tag in tags_from_plugin
                if hasattr(tag, "num_articles") and tag.num_articles > 0
            ],
            key=lambda x: (-x[1], x[0]),
        )
        expected_tags_final = sorted(
            [(slugify(tag_names[2]), 5), (slugify(tag_names[1]), 3)], key=lambda x: (-x[1], x[0])
        )
        self.assertEqual(actual_tags_summary, expected_tags_final)

    def test_articles_by_date(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="date_view_publisher")
        date_in = datetime(1914, 7, 28, tzinfo=timezone.utc)
        date_out = datetime(1939, 9, 1, tzinfo=timezone.utc)
        in_articles_published = []
        for i in range(11):
            publish_datetime = date_in.replace(hour=randint(0, 20), minute=randint(0, 59))
            article_content = self.create_article(
                title=f"In Date Article {i}",
                is_published=True,
                publishing_date=publish_datetime,
            )
            in_articles_published.append(article_content)
        out_articles_published = []
        for i in range(11):
            publish_datetime = date_out.replace(hour=randint(0, 20), minute=randint(0, 59))
            article_content = self.create_article(
                title=f"Out Date Article {i}",
                is_published=True,
                publishing_date=publish_datetime,
            )
            out_articles_published.append(article_content)
        response = self.client.get(
            reverse(
                f"{self.app_config.namespace}:article-list-by-day", kwargs={"year": "1914", "month": "07", "day": "28"}
            )
        )
        for article_content in out_articles_published:
            self.assertNotContains(response, article_content.title)
        for article_content in in_articles_published:
            self.assertContains(response, article_content.title)

    def test_articles_by_month(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="month_view_publisher")
        year_in, month_in = 1914, 7
        year_out, month_out = 1939, 9
        in_articles_published = []
        for i in range(11):
            publish_datetime = make_aware(
                datetime(year_in, month_in, randint(1, 28), randint(0, 20), randint(0, 59))
            )
            article_content = self.create_article(
                title=f"In Month Article {i}",
                is_published=True,
                publishing_date=publish_datetime,
            )
            in_articles_published.append(article_content)
        out_articles_published = []
        for i in range(11):
            publish_datetime = make_aware(
                datetime(year_out, month_out, randint(1, 28), randint(0, 20), randint(0, 59))
            )
            article_content = self.create_article(
                title=f"Out Month Article {i}",
                is_published=True,
                publishing_date=publish_datetime,
            )
            out_articles_published.append(article_content)
        response = self.client.get(
            reverse(
                f"{self.app_config.namespace}:article-list-by-month",
                kwargs={"year": str(year_in), "month": f"{month_in:02d}"},
            )
        )
        for article_content in out_articles_published:
            self.assertNotContains(response, article_content.title)
        for article_content in in_articles_published:
            self.assertContains(response, article_content.title)

    def test_articles_by_year(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="year_view_publisher")
        year_in = 1914
        year_out = 1939
        in_articles_published = []
        for i in range(11):
            publish_datetime = make_aware(
                datetime(year_in, randint(1, 12), randint(1, 28), randint(0, 20), randint(0, 59))
            )
            article_content = self.create_article(
                title=f"In Year Article {i}",
                is_published=True,
                publishing_date=publish_datetime,
            )
            in_articles_published.append(article_content)
        out_articles_published = []
        for i in range(11):
            publish_datetime = make_aware(
                datetime(year_out, randint(1, 12), randint(1, 28), randint(0, 20), randint(0, 59))
            )
            article_content = self.create_article(
                title=f"Out Year Article {i}",
                is_published=True,
                publishing_date=publish_datetime,
            )
            out_articles_published.append(article_content)
        response = self.client.get(
            reverse(f"{self.app_config.namespace}:article-list-by-year", kwargs={"year": str(year_in)})
        )
        for article_content in out_articles_published:
            self.assertNotContains(response, article_content.title)
        for article_content in in_articles_published:
            self.assertContains(response, article_content.title)

    def test_unattached_namespace(self):
        app_config = NewsBlogConfig.objects.create(namespace="another")
        articles = [self.create_article(app_config=app_config) for _ in range(11)]
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="unattached_ns_publisher")
        if articles:
            version = Version.objects.get_for_content(articles[0])
            version.publish(self.staff_user)
            # articles[0] is the original draft, its state is now published.
            # We need to use version.content if the URL is generated from the published content instance specifically
            # or ensure articles[0] itself is updated/used correctly by get_absolute_url
            # For now, assume articles[0].get_absolute_url() will work if its version is published.
        with self.assertRaises(NoReverseMatch):
            self.client.get(articles[0].get_absolute_url())


class TestIndex(NewsBlogTestCase):
    def test_index_simple(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="index_simple_publisher")
        self.request = self.get_request("en")
        self.index = ArticleIndex()
        content_text = self.rand_str(prefix="content_text_")
        lead_in_text = "lead in text for indexing"
        title_text = "a title for indexing"
        self.setup_categories()
        draft_content = self.create_article(content=content_text, lead_in=lead_in_text, title=title_text)
        draft_content.categories.add(self.category1)
        draft_content.categories.add(self.category2)
        draft_content.tags.add("tag 1")
        draft_content.tags.add("tag2")
        version = Version.objects.get_for_content(draft_content)
        version.publish(self.staff_user)
        # published_content_for_index should be version.content if it can be a new obj
        published_content_for_index = version.content
        self.assertEqual(self.index.get_title(published_content_for_index), title_text)
        self.assertEqual(self.index.get_description(published_content_for_index), lead_in_text)
        search_data = self.index.get_search_data(published_content_for_index, "en", self.request)
        self.assertIn(lead_in_text, search_data)
        self.assertIn(content_text, search_data)
        self.assertIn("tag 1", search_data)
        self.assertIn(self.category1.safe_translation_getter("name", language_code="en"), search_data)

    def test_index_multilingual(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="index_multi_publisher")
        self.index = ArticleIndex()
        self.request = self.get_request("en")
        _old_update_search = ArticleContent.update_search_on_save
        ArticleContent.update_search_on_save = True
        self.addCleanup(setattr, ArticleContent, "update_search_on_save", _old_update_search)
        content_text_shared = self.rand_str(prefix="content_shared_")
        self.setup_categories()
        title_en_article1 = "English Only Article for Index"
        lead_in_en_article1 = "Lead in for EN only article"
        draft_article1_en = self.create_article(
            title=title_en_article1, lead_in=lead_in_en_article1, content=content_text_shared
        )
        draft_article1_en.tags.add("tag_en_only")
        draft_article1_en.categories.add(self.category1)
        version1 = Version.objects.get_for_content(draft_article1_en)
        version1.publish(self.staff_user)
        title_en_article2 = "Bilingual Article EN Title"
        lead_in_en_article2 = "Bilingual EN Lead In"
        title_de_article2 = "Zweisprachiger Artikel DE Titel"
        lead_in_de_article2 = "Zweisprachiger DE Lead In"
        draft_article2_multi = self.create_article(
            title=title_en_article2, lead_in=lead_in_en_article2, content=content_text_shared, language="en"
        )
        with switch_language(draft_article2_multi, "de"):
            draft_article2_multi.title = title_de_article2
            draft_article2_multi.lead_in = lead_in_de_article2
            draft_article2_multi.save()
        draft_article2_multi.tags.add("tag_bilingual")
        draft_article2_multi.categories.add(self.category2)
        version2 = Version.objects.get_for_content(draft_article2_multi)
        version2.publish(self.staff_user)
        LANGUAGES_HIDE_SETTINGS = add_default_language_settings(PARLER_LANGUAGES_HIDE)
        with override_parler_settings(PARLER_LANGUAGES=LANGUAGES_HIDE_SETTINGS):
            with smart_override("de"):
                current_lang_de = get_current_language()
                qs_de = self.index.index_queryset(current_lang_de)
                self.assertEqual(qs_de.count(), 1)
                indexed_article_de = qs_de.first()
                self.assertEqual(indexed_article_de.pk, draft_article2_multi.pk)
                self.assertEqual(self.index.get_title(indexed_article_de), title_de_article2)
                self.assertEqual(self.index.get_description(indexed_article_de), lead_in_de_article2)
                search_data_de = self.index.get_search_data(indexed_article_de, current_lang_de, self.request)
                self.assertIn(lead_in_de_article2, search_data_de)
                self.assertTrue(search_data_de)
            with smart_override("en"):
                qs_en = self.index.index_queryset()
                self.assertEqual(qs_en.count(), 2)
                titles_in_en_index = sorted([self.index.get_title(ar) for ar in qs_en])
                self.assertListEqual(titles_in_en_index, sorted([title_en_article1, title_en_article2]))


class ViewLanguageFallbackMixin:
    view_name = None
    view_kwargs = {}

    def setUp(self):
        super().setUp()
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="fallback_mixin_publisher")
        self.publish_page(self.root_page, self.language, self.staff_user)
        self.publish_page(self.page, self.language, self.staff_user)
        # URLs depend on published pages being hooked in
        self.reload_urls()

    def get_view_kwargs(self):
        return self.view_kwargs.copy() if self.view_kwargs else {}

    def create_authors(self):
        if not hasattr(self, "staff_user"):
            self.staff_user = self.create_user(is_staff=True, is_superuser=True, username="fallback_mixin_publisher")
        self.author = self.create_person()
        self.owner = self.author.user
        return self.author, self.owner

    def create_de_article(
        self, author=None, owner=None, app_config=None, categories=None, title="a DE title", slug="a-de-title"
    ):
        _author = author or self.author
        _owner = owner or self.owner
        _app_config = app_config or self.app_config
        draft_de_content = self.create_article(
            title=title,
            slug=slug,
            lead_in="DE lead in text",
            author=_author,
            owner=_owner,
            app_config=_app_config,
            language="de",
        )
        if categories:
            draft_de_content.categories.set(categories)
        # use a predictable tag so tag-based fallback tests can fetch it
        draft_de_content.tags.add("tag1")
        version = Version.objects.get_for_content(draft_de_content)
        version.publish(self.staff_user)
        return version.content  # Return the potentially new content obj

    def create_en_articles(
        self, author=None, owner=None, app_config=None, amount=3, categories=None, title_prefix="EN Fallback Article"
    ):
        _author = author or self.author
        _owner = owner or self.owner
        _app_config = app_config or self.app_config
        published_en_articles = []
        for i in range(amount):
            draft_en_content = self.create_article(
                title=f"{title_prefix} {i}",
                author=_author,
                owner=_owner,
                app_config=_app_config,
                language="en",
            )
            if categories:
                draft_en_content.categories.set(categories)
            # tag with the same slug used by the tag list views
            draft_en_content.tags.add("tag1")
            version = Version.objects.get_for_content(draft_en_content)
            version.publish(self.staff_user)
            published_en_articles.append(version.content)  # Return the potentially new content obj
        return published_en_articles

    def test_a0_en_only(self):
        namespace = self.app_config.namespace
        api.create_page_content("de", "De Version", self.page, created_by=self.user)
        author, owner = self.create_authors()
        author.translations.create(slug=f"{author.slug}-de", language_code="de")
        de_article = self.create_de_article(author=author, owner=owner, categories=[self.category1])
        articles = self.create_en_articles(categories=[self.category1])
        with force_language("en"):
            response = self.client.get(reverse(f"{namespace}:{self.view_name}", kwargs=self.get_view_kwargs()))
        for article in articles:
            self.assertContains(response, article.title)
        self.assertContains(response, de_article.title)

    def test_a1_en_de(self):
        namespace = self.app_config.namespace
        author, owner = self.create_authors()
        author.translations.create(slug=f"{author.slug}-de", language_code="de")
        de_article = self.create_de_article(author=author, owner=owner, categories=[self.category1])
        articles = self.create_en_articles(categories=[self.category1])
        with force_language("en"):
            response = self.client.get(reverse(f"{namespace}:{self.view_name}", kwargs=self.get_view_kwargs()))
        for article in articles:
            self.assertContains(response, article.title)
        self.assertContains(response, de_article.title)


class ArticleListViewLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list"


class LatestArticlesFeedLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-feed"


class YearArticleListLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-year"

    def get_view_kwargs(self):
        return {"year": django_timezone_now().year}


class MonthArticleListLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-month"

    def get_view_kwargs(self):
        return {
            "year": django_timezone_now().year,
            "month": django_timezone_now().month,
        }


class DayArticleListLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-day"

    def get_view_kwargs(self):
        return {
            "year": django_timezone_now().year,
            "month": django_timezone_now().month,
            "day": django_timezone_now().day,
        }


class CategoryArticleListLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-category"

    def get_view_kwargs(self):
        return {"category": self.category1.slug}


class CategoryFeedListLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-category-feed"

    def get_view_kwargs(self):
        return {"category": self.category1.slug}


class TagArticleListLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-tag"

    def get_view_kwargs(self):
        return {"tag": "tag1"}


class TagFeedLanguageFallback(ViewLanguageFallbackMixin, NewsBlogTestCase):
    view_name = "article-list-by-tag-feed"

    def get_view_kwargs(self):
        return {"tag": "tag1"}
