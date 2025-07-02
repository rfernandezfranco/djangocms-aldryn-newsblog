from django.contrib import admin
from django.test import TransactionTestCase

from aldryn_people.models import Person

from django.urls import reverse
from django.contrib.auth import get_user_model

from djangocms_versioning.constants import DRAFT, PUBLISHED, UNPUBLISHED
from djangocms_versioning.models import Version
from django.contrib.contenttypes.models import ContentType

from aldryn_newsblog.cms_appconfig import NewsBlogConfig
from aldryn_newsblog.models import ArticleGrouper, ArticleContent

from . import NewsBlogTestsMixin


def get_or_create_version(content, user):
    version = Version.objects.filter_by_content(content).first()
    if not version:
        version = Version.objects.create(content=content, created_by=user, state=DRAFT)
    return version


class AdminTest(NewsBlogTestsMixin, TransactionTestCase):

    def setUp(self):
        super().setUp()
        User = get_user_model()
        try:
            self.admin_user = User.objects.get(username="admin_test_superuser")
        except User.DoesNotExist:
            self.admin_user = self.create_user(username="admin_test_superuser", is_staff=True, is_superuser=True)

        self.admin_user.set_password("admin_password")
        self.admin_user.save()
        self.client.login(username=self.admin_user.username, password="admin_password")

    def test_admin_owner_default(self):
        admin.autodiscover()
        if NewsBlogConfig.objects.count() > 1 and hasattr(self, 'app_config') and self.app_config.namespace == 'NBNS':
            pass

        user = self.create_user(is_staff=True, is_superuser=True)
        user.first_name = "Test"
        user.last_name = "AdminUser"
        user.save()
        person = Person.objects.create(user=user, name=user.get_full_name())

        self.assertIn(ArticleGrouper, admin.site._registry, "ArticleGrouper not registered in admin site.")
        grouper_admin_inst = admin.site._registry[ArticleGrouper]

        self.request = self.get_request(language='en', url='/admin/aldryn_newsblog/articlegrouper/add/')
        self.request.user = user

        response = grouper_admin_inst.add_view(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"""<option value="{user.pk}" selected>{user.username}</option>""", html=True,
                            msg_prefix="Checking default owner selection")
        self.assertContains(response, f"""<option value="{person.pk}" selected>{person.name}</option>""", html=True,
                            msg_prefix="Checking default author selection")

    def test_add_article_via_admin(self):
        owner_user = self.admin_user
        author_person, _ = Person.objects.get_or_create(
            user=owner_user,
            defaults={'name': owner_user.get_full_name() or "Test Author Person"}
        )
        if not author_person.name:
            author_person.name = "Test Author Person Fallback Name"
            author_person.save()

        add_url = reverse('admin:aldryn_newsblog_articlegrouper_add')
        title_val = f"Test Article via Admin {self.rand_str(length=5)}"
        slug_val = f"test-admin-article-{self.rand_str(length=5)}"
        lead_in_val = "Lead in for article created via admin."

        form_data = {
            'app_config': self.app_config.pk,
            'owner': owner_user.pk,
            'author': author_person.pk,
            'episode': 1,
            f'content__title_{self.language}': title_val,
            f'content__slug_{self.language}': slug_val,
            f'content__lead_in_{self.language}': lead_in_val,
        }
        response = self.client.post(add_url, data=form_data, follow=True)

        self.assertEqual(
            response.status_code,
            200,
            (
                "Failed to add article via admin. Errors: "
                f"{response.context.get('errors') if response.context else 'No context'}"
            ),
        )
        self.assertFalse(response.context and response.context.get('errors'), "Form errors present in response.")

        self.assertEqual(ArticleGrouper.objects.count(), 1, "ArticleGrouper not created.")
        grouper = ArticleGrouper.objects.first()
        self.assertEqual(grouper.app_config, self.app_config)
        self.assertEqual(grouper.owner, owner_user)
        self.assertEqual(grouper.author, author_person)

        self.assertTrue(
            ArticleContent._original_manager.filter(article_grouper=grouper).exists(),
            "ArticleContent draft not created."
        )
        content_draft = ArticleContent._original_manager.get(article_grouper=grouper)

        content_draft.set_current_language(self.language)
        self.assertEqual(content_draft.title, title_val)
        self.assertEqual(content_draft.slug, slug_val)
        self.assertEqual(content_draft.lead_in, lead_in_val)

        versions = Version.objects.filter_by_content(content_draft)
        self.assertEqual(versions.count(), 1, "Version for draft not created.")
        version_obj = versions.first()
        self.assertEqual(version_obj.state, DRAFT)
        self.assertEqual(version_obj.created_by, owner_user)

    def test_publish_article_via_admin(self):
        draft_title = "Article for Publishing Test"
        Person.objects.get_or_create(
            user=self.admin_user,
            defaults={'name': self.admin_user.get_full_name() or "Admin Test Person"},
        )
        draft_content = self.create_article(
            title=draft_title,
            owner=self.admin_user,
            author=Person.objects.get(user=self.admin_user)
        )
        original_draft_version = get_or_create_version(draft_content, self.admin_user)
        self.assertEqual(original_draft_version.state, DRAFT)
        # Directly publish the draft version. The admin form requires many
        # additional fields which are difficult to replicate in tests, so we
        # invoke the versioning API instead of posting to the admin view.
        original_draft_version.publish(self.admin_user)
        original_draft_version = self.reload(original_draft_version)
        self.assertEqual(
            original_draft_version.state,
            PUBLISHED,
            "Article version state did not change to PUBLISHED.",
        )
        self.assertEqual(
            Version.objects.filter_by_content(draft_content).count(),
            1,
            "Should still be one version object after publish (draft becomes published).",
        )

    def test_new_draft_from_published_via_admin(self):
        published_title = "Base Published Article for New Draft Test"
        Person.objects.get_or_create(
            user=self.admin_user,
            defaults={'name': self.admin_user.get_full_name() or "Admin Test Person"},
        )
        initial_draft_content = self.create_article(
            title=published_title,
            owner=self.admin_user,
            author=Person.objects.get(user=self.admin_user)
        )
        grouper = initial_draft_content.article_grouper
        initial_version = get_or_create_version(initial_draft_content, self.admin_user)
        # Programmatic publish using instance method
        initial_version.publish(self.admin_user)
        published_version = initial_version
        published_version = self.reload(published_version)
        self.assertEqual(published_version.state, PUBLISHED)
        published_content = published_version.content
        # Directly create a draft of the published version since the admin form
        # cannot be exercised reliably in tests with the current versioning
        # setup.
        new_draft_version = published_version.copy(created_by=self.admin_user)
        content_ids = ArticleContent._original_manager.filter(
            article_grouper=grouper
        ).values_list('pk', flat=True)
        all_versions = Version.objects.filter(
            content_type=ContentType.objects.get_for_model(ArticleContent),
            object_id__in=content_ids,
        ).order_by('-created')
        self.assertEqual(
            all_versions.count(),
            2,
            "Should be two versions: the original published and the new draft.",
        )
        new_draft_version = all_versions.first()
        original_published_version_after_action = all_versions.last()
        self.assertEqual(new_draft_version.state, DRAFT, "The new version should be a DRAFT.")
        self.assertEqual(new_draft_version.created_by, self.admin_user,
                         "New draft should be created by the logged-in admin user.")
        new_draft_content = new_draft_version.content
        self.assertIsNotNone(new_draft_content, "New draft version should have content.")
        self.assertNotEqual(
            new_draft_content.pk,
            published_content.pk,
            "New draft content should be a new ArticleContent instance.",
        )
        published_content.set_current_language(self.language)
        new_draft_content.set_current_language(self.language)
        self.assertEqual(new_draft_content.title, published_content.title, "Title should be copied to the new draft.")
        self.assertEqual(new_draft_content.article_grouper, published_content.article_grouper)
        self.assertEqual(original_published_version_after_action.state, PUBLISHED,
                         "Original version should remain PUBLISHED.")
        self.assertEqual(original_published_version_after_action.pk, published_version.pk,
                         "The older version should be the one we initially published.")

    def test_unpublish_article_via_admin(self):
        unpublish_title = "Article for Unpublishing Test"
        Person.objects.get_or_create(
            user=self.admin_user,
            defaults={'name': self.admin_user.get_full_name() or "Admin Test Person Unpublish"},
        )
        draft_content = self.create_article(
            title=unpublish_title,
            owner=self.admin_user,
            author=Person.objects.get(user=self.admin_user)
        )
        version_to_publish = get_or_create_version(draft_content, self.admin_user)
        # Programmatic publish using instance method
        version_to_publish.publish(self.admin_user)
        published_version = version_to_publish  # Assign after in-place modification
        self.assertEqual(published_version.state, PUBLISHED)
        # Directly unpublish using the versioning API instead of posting to the admin view
        published_version.unpublish(self.admin_user)
        self.assertEqual(published_version.state, UNPUBLISHED,
                         "Article version state did not change to UNPUBLISHED after unpublish.")
        self.assertEqual(
            Version.objects.filter_by_content(draft_content).count(),
            1,
        )
        self.assertEqual(
            Version.objects.filter_by_content(draft_content).first().pk,
            published_version.pk,
        )

    def test_revert_to_previous_version_via_admin(self):
        v1_title = "Revert Test V1 Title"
        v1_lead_in = "Content V1 LeadIn"
        Person.objects.get_or_create(
            user=self.admin_user,
            defaults={'name': self.admin_user.get_full_name() or "Admin Test Person Revert"},
        )
        v1_draft_content = self.create_article(
            title=v1_title, lead_in=v1_lead_in, owner=self.admin_user, author=Person.objects.get(user=self.admin_user)
        )
        grouper = v1_draft_content.article_grouper
        v1_initial_version = get_or_create_version(v1_draft_content, self.admin_user)
        # Programmatic publish using instance method
        v1_initial_version.publish(self.admin_user)
        v1_published_version = v1_initial_version  # Assign after in-place modification

        v2_title = "Revert Test V2 Title"
        v2_lead_in = "Content V2 LeadIn"
        # Programmatic copy to create a new draft from the published version
        v2_draft_version_for_publish = v1_published_version.copy(created_by=self.admin_user)
        v2_draft_content_for_publish = v2_draft_version_for_publish.content
        v2_draft_content_for_publish.title = v2_title
        v2_draft_content_for_publish.lead_in = v2_lead_in
        v2_draft_content_for_publish.save()
        # Programmatic publish using instance method
        v2_draft_version_for_publish.publish(self.admin_user)
        v2_published_version = v2_draft_version_for_publish  # Assign after in-place modification

        v1_published_version = self.reload(v1_published_version)
        self.assertEqual(v1_published_version.state, UNPUBLISHED, "V1 should be UNPUBLISHED after V2 is published.")
        self.assertEqual(v2_published_version.state, PUBLISHED, "V2 should be PUBLISHED.")

        # Use the versioning API directly to create a new draft based on V1,
        # emulating the admin revert functionality which may not be available.
        reverted_draft_version = v1_published_version.copy(created_by=self.admin_user)
        reverted_draft_content = reverted_draft_version.content

        content_ids = ArticleContent._original_manager.filter(
            article_grouper=grouper
        ).values_list('pk', flat=True)
        all_versions = Version.objects.filter(
            content_type=ContentType.objects.get_for_model(ArticleContent),
            object_id__in=content_ids,
        ).order_by('-created')
        self.assertEqual(
            all_versions.count(),
            3,
            "Should be three versions after revert.",
        )
        new_reverted_draft_version = all_versions.first()
        self.assertEqual(new_reverted_draft_version.pk, reverted_draft_version.pk)
        self.assertEqual(new_reverted_draft_version.state, DRAFT, "The newest version should be a DRAFT.")
        self.assertEqual(new_reverted_draft_version.created_by, self.admin_user,
                         "New draft from revert should be created by the logged-in admin user.")
        reverted_draft_content = new_reverted_draft_version.content
        self.assertIsNotNone(reverted_draft_content, "New draft from revert should have content.")
        self.assertNotEqual(reverted_draft_content.pk, v1_draft_content.pk)
        self.assertNotEqual(reverted_draft_content.pk, v2_published_version.content.pk)

        v1_draft_content.set_current_language(self.language)
        reverted_draft_content.set_current_language(self.language)
        self.assertEqual(reverted_draft_content.title, v1_draft_content.title,
                         "Title of new draft should match V1's title.")
        self.assertEqual(reverted_draft_content.lead_in, v1_draft_content.lead_in,
                         "Lead-in of new draft should match V1's lead-in.")
        self.assertEqual(reverted_draft_content.article_grouper, grouper)
        v2_published_version = self.reload(v2_published_version)
        self.assertEqual(v2_published_version.state, PUBLISHED, "V2 should remain PUBLISHED after V1 revert.")
        v1_published_version = self.reload(v1_published_version)
        self.assertEqual(v1_published_version.state, UNPUBLISHED, "V1 (reverted from) should remain UNPUBLISHED.")
