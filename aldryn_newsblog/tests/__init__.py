import os
import random
import string
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.test import RequestFactory
from django.urls import clear_url_caches
from django.utils.timezone import now
from django.utils.translation import override

from cms import api
from cms.apphook_pool import apphook_pool
from cms.appresolver import clear_app_resolvers
from cms.exceptions import AppAlreadyRegistered
from cms.models import PageContent
from cms.test_utils.testcases import CMSTestCase, TransactionCMSTestCase
from cms.toolbar.toolbar import CMSToolbar
from cms.utils.conf import get_cms_setting

from aldryn_categories.models import Category
from aldryn_people.models import Person
from djangocms_alias.models import Alias as AliasModel
from djangocms_alias.models import AliasContent
from djangocms_alias.models import Category as AliasCategory
from parler.utils.context import switch_language

from aldryn_newsblog.cms_apps import NewsBlogApp
# Changed Article to ArticleContent, added ArticleGrouper
from aldryn_newsblog.models import ArticleContent, ArticleGrouper, NewsBlogConfig


TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
TESTS_STATIC_ROOT = os.path.abspath(os.path.join(TESTS_ROOT, 'static'))


class NewsBlogTestsMixin:

    NO_REDIRECT_CMS_SETTINGS = {
        1: [
            {
                'code': 'de',
                'name': 'Deutsche',
                'fallbacks': ['en', ]  # FOR TESTING DO NOT ADD 'fr' HERE
            },
            {
                'code': 'fr',
                'name': 'Française',
                'fallbacks': ['en', ]  # FOR TESTING DO NOT ADD 'de' HERE
            },
            {
                'code': 'en',
                'name': 'English',
                'fallbacks': ['de', 'fr', ]
            },
            {
                'code': 'it',
                'name': 'Italiano',
                'fallbacks': ['fr', ]  # FOR TESTING, LEAVE AS ONLY 'fr'
            },
        ],
        'default': {
            'redirect_on_fallback': False,
        }
    }

    @staticmethod
    def reload(node):
        """NOTE: django-treebeard requires nodes to be reloaded via the Django
        ORM once its sub-tree is modified for the API to work properly.

        See:: https://tabo.pe/projects/django-treebeard/docs/2.0/caveats.html

        This is a simple helper-method to do that."""
        return node.__class__.objects.get(id=node.id)

    @classmethod
    def rand_str(cls, prefix='', length=23, chars=string.ascii_letters):
        return prefix + ''.join(random.choice(chars) for _ in range(length))

    @classmethod
    def create_user(cls, **kwargs):
        kwargs.setdefault('username', cls.rand_str())
        kwargs.setdefault('first_name', cls.rand_str())
        kwargs.setdefault('last_name', cls.rand_str())
        return User.objects.create(**kwargs)

    def create_person(self):
        return Person.objects.create(
            user=self.create_user(), slug=self.rand_str())

    def create_article(self, content=None, **kwargs):
        try:
            author = kwargs['author']
        except KeyError:
            author = self.create_person()
        try:
            owner = kwargs['owner']
        except KeyError:
            owner = author.user

        # Original fields for Article
        original_fields = {
            'title': self.rand_str(),
            'slug': self.rand_str(),
            'author': author,
            'owner': owner,
            'app_config': self.app_config,
            'publishing_date': now(), # This will be ignored for ArticleContent
            'is_published': True,   # This will be ignored for ArticleContent
        }
        original_fields.update(kwargs)

        # FIXME: This method needs complete rework for the ArticleGrouper/ArticleContent structure.
        # The following is a temporary adaptation to make makemigrations pass,
        # IT WILL NOT WORK FOR RUNNING ACTUAL TESTS.

        # 1. Create or get the ArticleGrouper
        # Extract fields relevant for ArticleGrouper
        grouper_kwargs = {
            'app_config': original_fields.get('app_config', self.app_config), # Fallback to self.app_config
            'owner': original_fields.get('owner', owner),
            'author': original_fields.get('author', author),
            # serial and episode would also go here if needed
        }
        # Ensure app_config is not None, which can happen if self.app_config is not set
        if not grouper_kwargs['app_config']:
            # This is a fallback, ideally app_config should always be valid in tests
            if NewsBlogConfig.objects.exists():
                grouper_kwargs['app_config'] = NewsBlogConfig.objects.first()
            else:
                # Cannot proceed if no app_config, this test helper is fundamentally broken without proper setup
                raise ValueError("Cannot create ArticleGrouper: app_config is missing and no default found.")

        article_grouper, _ = ArticleGrouper.objects.get_or_create(
            owner=grouper_kwargs['owner'],
            app_config=grouper_kwargs['app_config'],
            defaults=grouper_kwargs # a fuller set of defaults if creating
        )

        # 2. Create the ArticleContent, linking it to the grouper
        article_content_fields = {
            'title': original_fields.get('title'),
            'slug': original_fields.get('slug'),
            'article_grouper': article_grouper,
            # Add any other fields from original_fields that are now on ArticleContent, e.g. is_featured
            'is_featured': original_fields.get('is_featured', False),
            # lead_in, meta fields etc. would be passed via kwargs if needed
        }

        # Filter kwargs to only include valid fields for ArticleContent
        valid_content_field_names = {f.name for f in ArticleContent._meta.get_fields()}
        for key, value in kwargs.items():
            if key in valid_content_field_names and key not in article_content_fields:
                article_content_fields[key] = value

        article_content = ArticleContent.objects.create(**article_content_fields)
        # search_data calculation happens on save in the model, if implemented
        # article_content.save() # Already saved by create, unless search_data logic requires a second save.

        if content:
            api.add_plugin(article_content.content, 'TextPlugin',
                           self.language, body=content)
        return article_content

    def create_tagged_articles(self, num_articles=3, tags=('tag1', 'tag2'),
                               **kwargs):
        """Create num_articles Articles for each tag"""
        articles = {}
        for tag_name in tags:
            tagged_articles = []
            for _ in range(num_articles):
                article = self.create_article(**kwargs)
                article.save()
                article.tags.add(tag_name)
                tagged_articles.append(article)
            tag_slug = tagged_articles[0].tags.slugs()[0]
            articles[tag_slug] = tagged_articles
        return articles

    def setup_categories(self):
        """
        Sets-up i18n categories (self.category_root, self.category1 and
        self.category2) for use in tests
        """
        self.language = settings.LANGUAGES[0][0]

        categories = []
        # Set the default language, create the objects
        with override(self.language):
            code = f"{self.language}-"
            self.category_root = Category.add_root(
                name=self.rand_str(prefix=code, length=8))
            categories.append(self.category_root)
            self.category1 = self.category_root.add_child(
                name=self.rand_str(prefix=code, length=8))
            categories.append(self.category1)
            self.category2 = self.category_root.add_child(
                name=self.rand_str(prefix=code, length=8))
            categories.append(self.category2)

        # We should reload category_root, since we modified its children.
        self.category_root = self.reload(self.category_root)

        # Setup the other language(s) translations for the categories
        for language, _ in settings.LANGUAGES[1:]:
            for category in categories:
                with switch_language(category, language):
                    code = f"{language}-"
                    category.name = self.rand_str(prefix=code, length=8)
                    category.save()

    @staticmethod
    def get_request(language=None, url="/"):
        """
        Returns a Request instance populated with cms specific attributes.
        """
        request_factory = RequestFactory(HTTP_HOST=settings.ALLOWED_HOSTS[0])
        request = request_factory.get(url)
        request.session = {}
        request.LANGUAGE_CODE = language or settings.LANGUAGE_CODE
        # Needed for plugin rendering.
        request.current_page = None
        request.user = AnonymousUser()
        request.toolbar = CMSToolbar(request)
        return request

    def setUp(self):
        self.template = get_cms_setting('TEMPLATES')[0][0]
        self.language = settings.LANGUAGES[0][0]
        self.user, _ = get_user_model().objects.get_or_create(username="python-api")
        self.root_page = api.create_page(
            'root page',
            self.template,
            self.language,
            created_by=self.user
        )
        try:
            # Django-cms 3.5 doesn't set is_home when create_page is called
            self.root_page.set_as_homepage()
        except AttributeError:
            pass

        self.app_config = NewsBlogConfig.objects.language(self.language).create(
            app_title='news_blog',
            namespace='NBNS',
            paginate_by=15,
        )
        self.page = api.create_page(
            'page', self.template, self.language,
            parent=self.root_page,
            apphook='NewsBlogApp',
            apphook_namespace=self.app_config.namespace,
            created_by=self.user)
        self.plugin_page = api.create_page(
            title="plugin_page", template=self.template, language=self.language,
            parent=self.root_page, created_by=self.user)

        self.placeholder = self.page.get_admin_content(self.language).get_placeholders().first()

        self.setup_categories()

        for page in self.root_page, self.page:
            for language, _ in settings.LANGUAGES[1:]:
                api.create_page_content(language, page.get_slug(self.language), page, created_by=self.user)

    def publish_page(self, page, language, user):
        """Publish page content."""
        content = PageContent.admin_manager.get(page=page, language=language)
        version = content.versions.last()
        version.publish(user)

    def create_alias_content(self, static_code, language, category_name="test category", alias_name="test alias"):
        category = AliasCategory.objects.create(name=category_name)
        alias_obj = AliasModel.objects.get_or_create(
            static_code=static_code,
            category=category,
            # site__isnull=True,
        )[0]
        alias_content = AliasContent.objects.with_user(self.user).create(
            alias=alias_obj,
            name=alias_name,
            language=language,
        )
        return alias_content


class CleanUpMixin:
    apphook_object = None

    def setUp(self):
        super().setUp()
        apphook_object = self.get_apphook_object()
        self.reload_urls(apphook_object)

    def tearDown(self):
        """
        Do a proper cleanup, delete everything what is preventing us from
        clean environment for tests.
        :return: None
        """
        self.app_config.delete()
        self.reset_all()
        cache.clear()
        super().tearDown()

    def get_apphook_object(self):
        return self.apphook_object

    def reset_apphook_cmsapp(self, apphook_object=None):
        """
        For tests that should not be polluted by previous setup we need to
        ensure that app hooks are reloaded properly. One of the steps is to
        reset the relation between EventListAppHook and EventsConfig
        """
        if apphook_object is None:
            apphook_object = self.get_apphook_object()
        app_config = getattr(apphook_object, 'app_config', None)
        if app_config and getattr(app_config, 'cmsapp', None):
            delattr(apphook_object.app_config, 'cmsapp')
        if getattr(app_config, 'cmsapp', None):
            delattr(app_config, 'cmsapp')

    def reset_all(self):
        """
        Reset all that could leak from previous test to current/next test.
        :return: None
        """
        apphook_object = self.get_apphook_object()
        self.delete_app_module(apphook_object.__module__)
        self.reload_urls(apphook_object)
        self.apphook_clear()

    def delete_app_module(self, app_module=None):
        """
        Remove APP_MODULE from sys.modules. Taken from cms.
        :return: None
        """
        if app_module is None:
            apphook_object = self.get_apphook_object()
            app_module = apphook_object.__module__
        if app_module in sys.modules:
            del sys.modules[app_module]

    def apphook_clear(self):
        """
        Clean up apphook_pool and sys.modules. Taken from cms with slight
        adjustments and fixes.
        :return: None
        """
        try:
            apphooks = apphook_pool.get_apphooks()
        except AppAlreadyRegistered:
            # there is an issue with discover apps, or i'm using it wrong.
            # setting discovered to True solves it. Maybe that is due to import
            # from aldryn_events.cms_apps which registers EventListAppHook
            apphook_pool.discovered = True
            apphooks = apphook_pool.get_apphooks()

        for name, label in list(apphooks):
            if apphook_pool.apps[name].__class__.__module__ in sys.modules:
                del sys.modules[apphook_pool.apps[name].__class__.__module__]
        apphook_pool.clear()
        self.reset_apphook_cmsapp()

    def reload_urls(self, apphook_object=None):
        """
        Clean up url related things (caches, app resolvers, modules).
        Taken from cms.
        :return: None
        """
        if apphook_object is None:
            apphook_object = self.get_apphook_object()
        app_module = apphook_object.__module__
        package = app_module.split('.')[0]
        clear_app_resolvers()
        clear_url_caches()
        url_modules = [
            'cms.urls',
            f'{package}.urls',
            settings.ROOT_URLCONF
        ]

        for module in url_modules:
            if module in sys.modules:
                del sys.modules[module]


class NewsBlogTestCase(CleanUpMixin, NewsBlogTestsMixin, CMSTestCase):
    apphook_object = NewsBlogApp
    pass


class NewsBlogTransactionTestCase(CleanUpMixin,
                                  NewsBlogTestsMixin,
                                  TransactionCMSTestCase):
    apphook_object = NewsBlogApp
    pass
