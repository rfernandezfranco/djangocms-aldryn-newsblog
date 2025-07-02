import os
import random
import string
import sys

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.test import RequestFactory
from django.urls import clear_url_caches
from importlib import import_module
from django.utils.translation import override

from cms import api
from cms.apphook_pool import apphook_pool
from cms.appresolver import clear_app_resolvers
from cms.exceptions import AppAlreadyRegistered
from cms.models import PageContent
from cms.test_utils.testcases import CMSTestCase, TransactionCMSTestCase
from cms.toolbar.toolbar import CMSToolbar

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
        """Reload an instance from the database using the most permissive manager.

        Treebeard nodes and versioned models sometimes require using the
        ``_original_manager`` to bypass default query restrictions.  This helper
        mirrors the old behaviour of simply fetching the object again by ID but
        falls back to ``_original_manager`` when available.
        """
        model = node.__class__
        manager = getattr(model, "_original_manager", model.objects)
        return manager.get(id=node.id)

    @classmethod
    def rand_str(cls, prefix='', length=23, chars=string.ascii_letters):
        return prefix + ''.join(random.choice(chars) for _ in range(length))

    @classmethod
    def create_user(cls, **kwargs):
        from django.db.models import signals
        from cms.signals.permissions import post_save_user

        kwargs.setdefault('username', cls.rand_str())
        kwargs.setdefault('first_name', cls.rand_str())
        kwargs.setdefault('last_name', cls.rand_str())

        # Disable Django CMS' PageUser creation when saving users. The
        # additional objects are irrelevant for these tests and can trigger
        # FOREIGN KEY errors with transaction rollbacks.
        signals.post_save.disconnect(
            post_save_user,
            sender=User,
            dispatch_uid="cms_post_save_user",
        )
        try:
            user = User.objects.create(**kwargs)
        finally:
            signals.post_save.connect(
                post_save_user,
                sender=User,
                dispatch_uid="cms_post_save_user",
            )
        return user

    def create_person(self):
        user = self.create_user()
        person = Person(user=user)
        person.set_current_language(settings.LANGUAGES[0][0])
        person.name = f"{user.first_name} {user.last_name}".strip() or user.get_username()
        person.slug = self.rand_str()
        person.save()
        return person

    def create_article(self, content=None, **kwargs):
        # Determine owner for the grouper
        _owner = kwargs.pop('owner', None)
        if not _owner:
            if hasattr(self, 'user') and self.user.is_authenticated:  # self.user from CMSTestCase
                _owner = self.user
            else:  # Fallback to creating a new user
                _owner = self.create_user(is_staff=True, is_superuser=True)

        _app_config = kwargs.pop('app_config', self.app_config)  # Use self.app_config if available

        # Determine author for the grouper
        _author = kwargs.pop('author', None)
        if not _author:
            # If an explicit author (Person instance) is not passed,
            # try to find a Person linked to the _owner.
            try:
                _author = Person.objects.get(user=_owner)
            except Person.DoesNotExist:
                # Only auto-create when the app config opts in
                if _app_config.create_authors:
                    _author = Person(user=_owner)
                    _author.set_current_language(settings.LANGUAGES[0][0])
                    name = f"{_owner.first_name} {_owner.last_name}".strip() or _owner.get_username()
                    _author.name = name
                    _author.slug = self.rand_str()
                    _author.save()
                else:
                    _author = None
        _language = kwargs.pop('language', getattr(self, 'language', settings.LANGUAGES[0][0]))
        _title = kwargs.pop('title', self.rand_str(prefix="Test Article "))

        # Grouper specific kwargs can be passed in via 'grouper_kwargs'
        grouper_extra_kwargs = kwargs.pop('grouper_kwargs', {})
        grouper = ArticleGrouper.objects.create(
            owner=_owner,
            author=_author,
            app_config=_app_config,
            **grouper_extra_kwargs
        )

        # Remaining kwargs are for ArticleContent.
        # Pop fields that are not on ArticleContent or are handled separately.
        publishing_date = kwargs.pop('publishing_date', None)  # Not used yet
        is_published = kwargs.pop('is_published', False)

        # Create the initial ArticleContent (this will be the DRAFT version)
        content_fields = {
            'article_grouper': grouper,
            'is_featured': kwargs.pop('is_featured', False),  # Example direct field
            # Any other direct fields for ArticleContent can be set from kwargs here
        }
        # Add remaining kwargs that are valid for ArticleContent
        valid_content_field_names = {
            f.name
            for f in ArticleContent._meta.get_fields()
            if f.name not in ['translations', 'pk', 'id']
        }
        for key, value in kwargs.items():
            if key in valid_content_field_names:
                content_fields[key] = value

        article_content = ArticleContent(**content_fields)

        # Set translated fields
        article_content.set_current_language(_language)
        article_content.title = _title
        article_content.slug = kwargs.get('slug', None)  # Allow passing slug, or let auto-slug work
        article_content.lead_in = kwargs.get('lead_in', '')
        # ... other translated fields can be added from kwargs similarly ...

        article_content.save()  # This creates the draft version and translations

        # Explicitly create a version if one doesn't exist (diagnostic/workaround)
        from djangocms_versioning.models import Version
        from djangocms_versioning.constants import DRAFT
        version = Version.objects.create(
            content=article_content,
            created_by=_owner,
            state=DRAFT,
        )
        if is_published:
            version.publish(_owner)
        if publishing_date:
            version.created = publishing_date
            version.save(update_fields=['created'])

        if content:  # 'content' here refers to placeholder content string
            api.add_plugin(article_content.content, 'TextPlugin',
                           _language, body=content)
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
        self.template = 'page.html'  # Explicitly use the created test template
        self.language = settings.LANGUAGES[0][0]
        # Use create_user to avoid potential IntegrityError with get_or_create in some test cases
        self.user = self.create_user(
            username="testmixin_user",
            is_staff=True,
            is_superuser=False,
        )  # Basic user for most tests

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
        if version is None:
            from djangocms_versioning.models import Version
            from djangocms_versioning.constants import DRAFT

            version = Version.objects.create(content=content, created_by=user, state=DRAFT)
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

        # Django CMS attaches a signal that creates ``PageUser`` rows whenever
        # a ``User`` is saved when permissions are enabled.  These extra objects
        # are unnecessary for our tests and can cause FOREIGN KEY errors when
        # the database is reused, so disconnect the handler.
        from cms.signals.permissions import post_save_user
        from django.contrib.auth import get_user_model
        from django.db.models import signals

        signals.post_save.disconnect(
            post_save_user,
            sender=get_user_model(),
            dispatch_uid="cms_post_save_user",
        )

    def tearDown(self):
        """
        Do a proper cleanup, delete everything what is preventing us from
        clean environment for tests.
        :return: None
        """
        from djangocms_versioning.models import Version
        from cms.models.permissionmodels import PageUser, PageUserGroup

        # Version objects reference each other via the ``source`` field using a
        # ``PROTECT`` relationship. Deleting them in bulk triggers
        # ``ProtectedError`` because Django tries to delete a version before the
        # one that points to it. Break those links first and then remove the
        # objects so teardown can proceed cleanly.
        Version.objects.all().update(source=None)
        Version.objects.all().delete()
        PageUser.objects.all().delete()
        PageUserGroup.objects.all().delete()

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
        # Import modules again so that url patterns and apphooks are registered
        for module in url_modules:
            import_module(module)


class NewsBlogTestCase(CleanUpMixin, NewsBlogTestsMixin, CMSTestCase):
    apphook_object = NewsBlogApp
    pass


class NewsBlogTransactionTestCase(CleanUpMixin,
                                  NewsBlogTestsMixin,
                                  TransactionCMSTestCase):
    apphook_object = NewsBlogApp
    pass
