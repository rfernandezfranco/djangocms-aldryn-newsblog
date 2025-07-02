from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.translation import get_language_from_request
from django.utils.translation import gettext as _

from aldryn_apphooks_config.utils import get_app_instance
from aldryn_categories.models import Category

from aldryn_newsblog.models import ArticleContent, ArticleGrouper, NewsBlogConfig # Changed Article
from aldryn_newsblog.utils.utilities import get_valid_languages


class LatestArticlesFeed(Feed):

    def __call__(self, request, *args, **kwargs):
        self.namespace, self.config = get_app_instance(request)
        language = get_language_from_request(request)
        site_id = getattr(get_current_site(request), 'id', None)
        self.valid_languages = get_valid_languages(
            self.namespace,
            language_code=language,
            site_id=site_id)
        return super().__call__(
            request, *args, **kwargs)

    def link(self):
        return reverse(f'{self.namespace}:article-list-feed')

    def title(self):
        msgformat = {'site_name': Site.objects.get_current().name}
        return _('Articles on %(site_name)s') % msgformat

    def get_queryset(self):
        from django.contrib.contenttypes.models import ContentType
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version
        from django.utils import timezone
        from django.db.models import Subquery

        app_config = getattr(self, 'config', None)
        content_type = ContentType.objects.get_for_model(ArticleContent)

        published_content_pks_query = Version.objects.filter(
            content_type=content_type,
            state=PUBLISHED,
            created__lte=timezone.now()
        ).values_list('object_id', flat=True).distinct()

        qs = ArticleContent.objects.filter(pk__in=Subquery(published_content_pks_query))

        if app_config:
            qs = qs.filter(article_grouper__app_config=app_config)

        # The self.valid_languages is set in __call__ and should be used for translation filtering.
        if self.valid_languages:
            qs = qs.translated(*self.valid_languages)
        return qs

    def items(self): # obj parameter is not used by base Feed.items, removing it.
        from django.contrib.contenttypes.models import ContentType
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version
        from django.db.models import Subquery, OuterRef

        qs = self.get_queryset()

        content_type = ContentType.objects.get_for_model(ArticleContent)
        version_published_date_subquery = Subquery(
            Version.objects.filter(
                object_id=OuterRef('pk'),
                content_type=content_type,
                state=PUBLISHED
            ).order_by('-created').values('created')[:1]
        )

        qs = qs.annotate(
            version_published_date=version_published_date_subquery
        ).order_by('-version_published_date')[:10]
        return qs

    def item_title(self, item: ArticleContent):
        return item.title

    def item_description(self, item: ArticleContent):
        return item.lead_in

    def item_pubdate(self, item: ArticleContent):
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version

        if hasattr(item, 'version_published_date') and item.version_published_date:
            return item.version_published_date
        else:
            # Fallback, though items() should always annotate.
            try:
                version = Version.objects.get_for_content(item)
                if version.state == PUBLISHED:
                    return version.created
            except Version.DoesNotExist:
                return None


class TagFeed(LatestArticlesFeed):

    def get_object(self, request, tag):
        return tag

    def items(self, obj):
        return self.get_queryset().filter(tags__slug=obj)[:10]


class CategoryFeed(LatestArticlesFeed):

    def get_object(self, request, category):
        language = get_language_from_request(request, check_path=True)
        return Category.objects.language(language).translated(
            *self.valid_languages, slug=category).get()

    def items(self, obj):
        return self.get_queryset().filter(categories=obj)[:10]
