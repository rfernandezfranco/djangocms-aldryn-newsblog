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
        # FIXME #VERSIONING: .published() and namespace() are not standard model managers.
        # Need to filter by published versions and app_config on ArticleGrouper.
        # app_config is on ArticleGrouper.
        qs = ArticleContent.objects.filter(
            article_grouper__app_config__namespace=self.namespace
        ).translated(*self.valid_languages)
        return qs

    def items(self, obj):
        qs = self.get_queryset()
        # FIXME #VERSIONING: publishing_date is no longer on ArticleContent.
        # Order by version's publish date. For now, ordering by grouper PK.
        return qs.order_by('-article_grouper__pk')[:10] # Changed from publishing_date

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.lead_in

    def item_pubdate(self, item):
        # FIXME #VERSIONING: publishing_date is no longer on ArticleContent.
        # Needs to come from Version object. Placeholder.
        return None # Was: item.publishing_date


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
