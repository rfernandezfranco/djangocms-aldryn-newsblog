from aldryn_apphooks_config.models import AppHookConfig
from cms.app_base import CMSAppConfig
from .models import Article
from .rendering import render_article_content
class NewsBlogCMSConfig(CMSAppConfig):
    cms_enabled = True
    cms_toolbar_enabled_models = [(Article, render_article_content)]
    moderated_models = [Article]
    app_config = AppHookConfig
    reference_fields = [
        (Article, 'content'),
    ]
    def get_urls(self, page=None, language=None, **kwargs):
        return ["aldryn_newsblog.urls"]
    def get_configs(self):
        return self.app_config.objects.all()
    def get_config(self, namespace):
        try:
            return self.app_config.objects.get(namespace=namespace)
        except ObjectDoesNotExist:
            return None
    def get_config_add_url(self):
        try:
            return reverse("admin:{}_{}_add".format(self.app_config._meta.app_label, self.app_config._meta.model_name))
        except AttributeError:
            return reverse(
                "admin:{}_{}_add".format(self.app_config._meta.app_label, self.app_config._meta.module_name)
            )
