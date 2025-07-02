from django.apps import AppConfig


def aldryn_news_urls_need_reloading(sender, **kwargs) -> None:
    """Reload urls when Sestion is added or removed."""
    from django.urls import clear_url_caches

    from cms.appresolver import clear_app_resolvers
    clear_app_resolvers()
    clear_url_caches()


class AldrynNewsBlog(AppConfig):
    name = 'aldryn_newsblog'
    verbose_name = 'Aldryn News & Blog'

    def ready(self):
        from cms.signals import urls_need_reloading
        urls_need_reloading.connect(aldryn_news_urls_need_reloading)

        # djangocms-versioning 2.x renamed some manager helpers.  Older tests
        # expect ``Version.objects.filter_by_content`` so add a shim when
        # running against newer releases.
        from djangocms_versioning.models import Version, VersionQuerySet
        from django.contrib.contenttypes.models import ContentType

        if not hasattr(Version.objects, "filter_by_content"):
            def filter_by_content(self, content):
                ct = ContentType.objects.get_for_model(type(content))
                return self.filter(content_type=ct, object_id=content.pk)

            Version.objects.filter_by_content = filter_by_content.__get__(Version.objects)
            VersionQuerySet.filter_by_content = filter_by_content
