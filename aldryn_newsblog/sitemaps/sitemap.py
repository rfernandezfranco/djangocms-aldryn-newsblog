from aldryn_translation_tools.sitemaps import I18NSitemap

from ..models import ArticleContent # Changed Article to ArticleContent


class NewsBlogSitemap(I18NSitemap):

    changefreq = "never"
    priority = 0.5

    def __init__(self, *args, **kwargs):
        self.namespace = kwargs.pop('namespace', None)
        super().__init__(*args, **kwargs)

    def items(self):
        # FIXME: .published() manager method needs to be re-evaluated for versioning.
        # app_config is now on ArticleGrouper. This query needs to be adapted.
        qs = ArticleContent.objects.all() # Changed from Article.objects.published()
        if self.language is not None:
            qs = qs.translated(self.language)
        if self.namespace is not None:
            qs = qs.filter(article_grouper__app_config__namespace=self.namespace) # Adjusted filter path
        return qs

    def lastmod(self, obj):
        # FIXME: publishing_date is no longer on ArticleContent.
        # This needs to get the publication date from the djangocms-versioning Version object.
        # Returning None as a placeholder.
        return None # Was: obj.publishing_date
