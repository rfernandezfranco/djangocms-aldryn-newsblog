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
