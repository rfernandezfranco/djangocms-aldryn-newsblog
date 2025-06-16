# -*- coding: utf-8 -*-
from django.conf import settings
from django.core.management.base import BaseCommand

from parler.utils.context import switch_language

from aldryn_newsblog.models import ArticleContent # Changed Article to ArticleContent
# Imports for versioning-aware query
from django.contrib.contenttypes.models import ContentType
from djangocms_versioning.constants import PUBLISHED
from djangocms_versioning.models import Version
from django.utils import timezone


class Command(BaseCommand):
    can_import_settings = True

    def add_arguments(self, parser):
        parser.add_argument(
            '-l',
            '--language',
            action='append',
            dest='languages',
            default=None,
        )

    def handle(self, *args, **options):
        languages = options.get('languages')

        if languages is None:
            languages = [language[0] for language in settings.LANGUAGES]

        # ArticleContentTranslation (Parler model for ArticleContent)
        translation_model = ArticleContent._parler_meta.root_model # Changed Article to ArticleContent

        # Iterate over currently published ArticleContent instances
        content_type_ac = ContentType.objects.get_for_model(ArticleContent)
        published_content_pks = Version.objects.filter(
            content_type=content_type_ac,
            state=PUBLISHED,
            published__lte=timezone.now()  # Ensure it's currently published
        ).values_list('object_id', flat=True).distinct()

        for article_content in ArticleContent.objects.filter(pk__in=published_content_pks):
            translations = article_content.translations.filter(
                language_code__in=languages
            )

            # build internal parler cache
            parler_cache = dict(
                (trans.language_code, trans) for trans in translations)

            # set internal parler cache
            # to avoid parler hitting db for every language
            article_content._translations_cache[translation_model] = parler_cache

            for translation in translations:
                language = translation.language_code

                with switch_language(article_content, language_code=language): # Changed article to article_content
                    translation.search_data = article_content.get_search_data() # Changed article to article_content
                    # make sure to only update the search_data field
                    translation.save(update_fields=["search_data"])
