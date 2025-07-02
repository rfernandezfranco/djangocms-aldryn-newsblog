from aldryn_translation_tools.sitemaps import I18NSitemap

from ..models import ArticleContent  # Changed Article to ArticleContent


class NewsBlogSitemap(I18NSitemap):

    changefreq = "never"
    priority = 0.5

    def __init__(self, *args, **kwargs):
        self.namespace = kwargs.pop('namespace', None)
        super().__init__(*args, **kwargs)

    def items(self):
        from django.contrib.contenttypes.models import ContentType
        from djangocms_versioning.constants import PUBLISHED
        from djangocms_versioning.models import Version
        from django.utils import timezone
        from django.db.models import Subquery, OuterRef

        content_type = ContentType.objects.get_for_model(ArticleContent)

        # Get PKs of ArticleContent that have a currently published version
        published_content_pks_qs = Version.objects.filter(
            content_type=content_type,
            state=PUBLISHED,
            created__lte=timezone.now()
        ).values_list('object_id', flat=True).distinct()

        # Base queryset of published ArticleContent
        qs = ArticleContent.objects.filter(pk__in=published_content_pks_qs)

        if self.language is not None:
            qs = qs.translated(self.language)  # Filter by sitemap language if specified

        if self.namespace is not None:
            qs = qs.filter(article_grouper__app_config__namespace=self.namespace)

        # Annotate with the published date from the version for ordering and for lastmod
        version_published_date_subquery = Subquery(
            Version.objects.filter(
                object_id=OuterRef('pk'),
                content_type=content_type,
                state=PUBLISHED
            ).order_by('-created').values('created')[:1]
        )

        return qs.annotate(
            version_published_date=version_published_date_subquery
        ).order_by('-version_published_date')  # Order by most recently published

    def lastmod(self, obj: ArticleContent):
        # obj is an ArticleContent instance passed by sitemap framework from items()
        # It should have 'version_published_date' annotated by the items() method.
        if hasattr(obj, 'version_published_date') and obj.version_published_date:
            return obj.version_published_date
        else:
            # Fallback if annotation is missing (should ideally not happen)
            from djangocms_versioning.constants import PUBLISHED
            from djangocms_versioning.models import Version
            try:
                # Fetch the latest published version for this content object
                # This is a fallback and might be less efficient than relying on annotation
                version = Version.objects.filter_by_content(obj).filter(state=PUBLISHED).latest('created')
                return version.created
            except Version.DoesNotExist:
                return None
