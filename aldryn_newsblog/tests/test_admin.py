from django.contrib import admin
from django.test import TransactionTestCase

from aldryn_people.models import Person

from django.urls import reverse
from django.contrib.auth import get_user_model

from djangocms_versioning.constants import DRAFT
from djangocms_versioning.models import Version

from aldryn_newsblog.cms_appconfig import NewsBlogConfig
# Updated model import: ArticleGrouper, ArticleContent
from aldryn_newsblog.models import ArticleGrouper, ArticleContent

from . import NewsBlogTestsMixin


class AdminTest(NewsBlogTestsMixin, TransactionTestCase):

    def setUp(self):
        # Ensure self.superuser is created and available if not already by NewsBlogTestsMixin
        # NewsBlogTestsMixin creates self.user, let's ensure it's a superuser for admin tests.
        # self.user from CMSTestCase is not a superuser by default.
        super().setUp() # Call NewsBlogTestsMixin's setUp
        User = get_user_model()
        try:
            self.admin_user = User.objects.get(username="admin_test_superuser")
        except User.DoesNotExist:
            self.admin_user = self.create_user(username="admin_test_superuser", is_staff=True, is_superuser=True)

        # Log in the admin user for self.client tests
        # self.client.login(username=self.admin_user.username, password='password') # Assuming 'password' if create_user doesn't set one.
        # create_user in NewsBlogTestsMixin does not set a known password.
        # For admin client tests, it's often better to force login or use a request factory with a user.
        # The existing test test_admin_owner_default uses a request factory.
        # For self.client.post, login is needed. Let's set a known password.
        self.admin_user.set_password("admin_password")
        self.admin_user.save()
        self.client.login(username=self.admin_user.username, password="admin_password")


    def test_admin_owner_default(self):
        # admin.autodiscover() is typically not needed in modern Django test setups if apps are correctly loaded.
        # If admin site isn't populated, it might be due to test runner setup or missing admin.autodiscover() call
        # in the project's urls.py or similar. For now, assume admin.site._registry is populated.

        # Ensure admin site is populated for the test environment
        admin.autodiscover()

        # Config selection logic:
        # The original test deleted extra NewsBlogConfig instances to ensure one was pre-selected.
        # This logic should still apply if multiple configs exist and one needs to be default in add view.
        # For ArticleGrouper, the app_config is a key part.
        if NewsBlogConfig.objects.count() > 1 and hasattr(self, 'app_config') and self.app_config.namespace == 'NBNS':
            # If self.app_config from NewsBlogTestsMixin setup exists and is 'NBNS',
            # and there's another one, this might be complex.
            # Let's simplify: ensure only ONE config for this test or ensure the target one is default.
            # For now, we'll assume the default app_config from setUp is used or is the only one.
            # If the test specifically relies on *which* app_config is auto-selected when multiple exist,
            # that part of the test might need more specific setup.
            # The main point is testing owner/author defaults.
            pass # Revisit if app_config selection becomes an issue.

        user = self.create_user(is_staff=True, is_superuser=True) # Ensure staff/superuser for admin access
        # self.client.login(username=user.username, password='password') # if using admin client

        # Create a Person associated with this user to be the default author
        # Ensure name is set as get_full_name() is used in assertion.
        user.first_name = "Test"
        user.last_name = "AdminUser"
        user.save()
        person = Person.objects.create(user=user, name=user.get_full_name())

        # Target ArticleGrouperAdmin
        self.assertIn(ArticleGrouper, admin.site._registry, "ArticleGrouper not registered in admin site.")
        grouper_admin_inst = admin.site._registry[ArticleGrouper]

        # Prepare request for the add view
        self.request = self.get_request(language='en', url='/admin/aldryn_newsblog/articlegrouper/add/')
        self.request.user = user
        # self.request.META['HTTP_HOST'] = 'example.com' # get_request sets HTTP_HOST via settings.ALLOWED_HOSTS

        response = grouper_admin_inst.add_view(self.request)

        # Check that the response is successful and contains the form
        self.assertEqual(response.status_code, 200)

        # Check for default owner (User) selection
        # The value in the option tag should be user.pk
        # The text content of the option tag should be user.username or user.get_full_name()
        # Based on Django admin, it's typically username for User foreign keys.
        self.assertContains(response, f"""<option value="{user.pk}" selected>{user.username}</option>""", html=True,
                            msg_prefix="Checking default owner selection")

        # Check for default author (Person) selection
        # The value in the option tag should be person.pk
        # The text content should be person's string representation (e.g., name)
        self.assertContains(response, f"""<option value="{person.pk}" selected>{person.name}</option>""", html=True,
                            msg_prefix="Checking default author selection")

    def test_add_article_via_admin(self):
        """
        Tests creating a new Article (Grouper + initial Draft Content) via the admin interface.
        """
        # Ensure an author and owner exist for form data
        # Use self.admin_user (created in setUp) as the owner
        owner_user = self.admin_user
        author_person, _ = Person.objects.get_or_create(
            user=owner_user,
            defaults={'name': owner_user.get_full_name() or "Test Author Person"}
        )
        if not author_person.name: # Ensure name is set if user didn't have first/last
            author_person.name = "Test Author Person Fallback Name"
            author_person.save()


        add_url = reverse('admin:aldryn_newsblog_articlegrouper_add')

        # Form data for ArticleGrouper and initial ArticleContent (draft)
        # Field names for ArticleContent are typically direct, but Parler fields need language suffix.
        # Example: 'title_en', 'slug_en'
        # The self.language is set in NewsBlogTestsMixin's setUp (e.g., 'en')
        title_val = f"Test Article via Admin {self.rand_str(length=5)}"
        slug_val = f"test-admin-article-{self.rand_str(length=5)}" # Slug must be unique
        lead_in_val = "Lead in for article created via admin."

        form_data = {
            'app_config': self.app_config.pk,
            'owner': owner_user.pk,
            'author': author_person.pk,
            # ArticleContent fields (assuming default language from self.language)
            # These names assume ExtendedGrouperVersionAdminMixin integrates them directly
            f'title_{self.language}': title_val,
            f'slug_{self.language}': slug_val,
            f'lead_in_{self.language}': lead_in_val,
            # Placeholder for content is usually handled by adding plugins after creation,
            # or if it's a simple CharField/TextField, it would be named e.g. 'content_en'
            # For now, we'll focus on title, slug, lead_in.
            # Potentially required by ArticleContent form (check model definition):
            # 'meta_title_en', 'meta_description_en', 'meta_keywords_en',
            # 'meta_canonical_en', 'meta_robots_en',
            # 'og_title_en', 'og_description_en', 'og_image_en', 'og_type_en',
            # 'twitter_title_en', 'twitter_description_en', 'twitter_image_en', 'twitter_card_en',
            # These might have defaults or not be strictly required on initial save.
        }

        response = self.client.post(add_url, data=form_data, follow=True)

        self.assertEqual(response.status_code, 200, f"Failed to add article via admin. Errors: {response.context.get('errors') if response.context else 'No context'}")
        if response.context and response.context.get('errors'):
             print(f"Admin form errors: {response.context.get('errors')}")
        self.assertFalse(response.context and response.context.get('errors'), "Form errors present in response.")
        # A more specific success message check could be:
        # self.assertContains(response, "The article grouper “Test Article via Admin” was added successfully.")

        self.assertEqual(ArticleGrouper.objects.count(), 1, "ArticleGrouper not created.")
        grouper = ArticleGrouper.objects.first()
        self.assertEqual(grouper.app_config, self.app_config)
        self.assertEqual(grouper.owner, owner_user)
        self.assertEqual(grouper.author, author_person)

        self.assertTrue(ArticleContent.objects.filter(article_grouper=grouper).exists(), "ArticleContent draft not created.")
        content_draft = ArticleContent.objects.get(article_grouper=grouper)

        # Verify translated fields on the content draft
        content_draft.set_current_language(self.language)
        self.assertEqual(content_draft.title, title_val)
        self.assertEqual(content_draft.slug, slug_val) # Check if slug was saved as provided or auto-generated
        self.assertEqual(content_draft.lead_in, lead_in_val)

        versions = Version.objects.filter_by_content(content_draft)
        self.assertEqual(versions.count(), 1, "Version for draft not created.")
        version_obj = versions.first()
        self.assertEqual(version_obj.state, DRAFT)
        self.assertEqual(version_obj.created_by, owner_user)

    def test_publish_article_via_admin(self):
        """
        Tests publishing a draft article via an admin action on the ArticleGrouper change view.
        """
        # 1. Create a draft article programmatically
        # self.admin_user is available from setUp and is logged in
        draft_title = "Article for Publishing Test"
        draft_content = self.create_article(
            title=draft_title,
            owner=self.admin_user, # Grouper owner
            author=Person.objects.get(user=self.admin_user) # Author, assuming person exists for admin_user
        )
        grouper = draft_content.article_grouper
        original_draft_version = Version.objects.get_for_content(draft_content)
        self.assertEqual(original_draft_version.state, DRAFT)

        # 2. Get the ArticleGrouper change view URL
        grouper_change_url = reverse('admin:aldryn_newsblog_articlegrouper_change', args=[grouper.pk])

        # 3. Simulate the Publish Action
        # This is an assumption. The actual field name for the publish action might be different.
        # Common patterns: '_publish', 'publish_item', or specific to djangocms-versioning.
        # For djangocms-versioning, the action is often tied to a specific button's name/value attribute
        # which might be something like "Publish" or an internal action name.
        # Let's assume the action is named 'publish' as per VersioningAdminMixin publish_item method.
        # The ExtendedGrouperVersionAdminMixin uses `_publish` in its `response_action`
        # and `publish_item_view` expects 'publish' in POST. Let's try `_publish`.

        # To correctly simulate the POST request that the "Publish" button triggers,
        # we might need to include all form fields that are part of the change form,
        # not just the action field. However, many admin actions are designed to work
        # with just the action field and the object's PK (which is in the URL).

        # First, try a simple POST with just the action.
        # The value for the action button (e.g., "Publish") might also be important.
        publish_form_data = {
            '_publish': 'Publish',
        }

        response = self.client.post(grouper_change_url, data=publish_form_data, follow=True)

        self.assertEqual(response.status_code, 200, f"Publish POST request failed. Errors: {response.context.get('errors') if response.context else 'No context'}")
        if response.context and response.context.get('errors'):
             print(f"Admin form errors on publish: {response.context.get('errors')}")
        # Check for a success message (these can be fragile but good for confirmation)
        self.assertContains(response, "The article content draft was published successfully.",
                            msg_prefix="Success message for publish not found.")


        # 4. Assert the Outcome
        original_draft_version.refresh_from_db() # Refresh to get the latest state
        self.assertEqual(original_draft_version.state, PUBLISHED, "Article version state did not change to PUBLISHED.")

        # Verify that the created_by on the version still reflects the initial creator of the version,
        # and not necessarily the publisher. The `Version.publisher` field (if it exists) or a log entry
        # would typically store the user who performed the publish action.
        # The `created_by` on the Version object is who created the Version object itself.
        # djangocms-versioning's publish operation updates the existing draft version to PUBLISHED.
        # So, original_draft_version.created_by should remain the same.
        # The user who clicked publish is usually logged by djangocms-versioning in its audit log if enabled.
        # For now, just checking the state is PUBLISHED is the primary goal.

        # Optional: Check if a new version was created or if the existing one was updated.
        # djangocms-versioning typically updates the existing draft version to published.
        self.assertEqual(Version.objects.filter_by_content(draft_content).count(), 1,
                         "Should still be one version object after publish (draft becomes published).")

    def test_new_draft_from_published_via_admin(self):
        """
        Tests creating a new draft from a published article via an admin action.
        """
        # 1. Create and publish an article programmatically
        published_title = "Base Published Article for New Draft Test"
        # Ensure Person object exists for self.admin_user for create_article helper
        Person.objects.get_or_create(user=self.admin_user, defaults={'name': self.admin_user.get_full_name() or "Admin Test Person"})

        initial_draft_content = self.create_article(
            title=published_title,
            owner=self.admin_user,
            author=Person.objects.get(user=self.admin_user)
        )
        grouper = initial_draft_content.article_grouper

        # Publish it using the versioning API
        from djangocms_versioning import api as versioning_api
        initial_version = Version.objects.get_for_content(initial_draft_content)
        versioning_api.publish(initial_version, self.admin_user)

        # After publishing, initial_version is now the published_version
        published_version = initial_version
        published_version.refresh_from_db()
        self.assertEqual(published_version.state, PUBLISHED)
        published_content = published_version.content # This is initial_draft_content

        # 2. Get the ArticleGrouper change view URL
        grouper_change_url = reverse('admin:aldryn_newsblog_articlegrouper_change', args=[grouper.pk])

        # 3. Simulate the "Create/Edit Draft" Action
        # This action in djangocms-versioning is typically named 'edit_draft'.
        # It creates a new draft if one doesn't exist, or redirects to the existing draft's edit page.
        create_draft_form_data = {
            'edit_draft': 'Edit draft', # This is an assumption for the action name
        }

        # This POST should redirect to the edit view of the new draft content.
        # For this test, we are primarily interested in the creation of the new draft version.
        response = self.client.post(grouper_change_url, data=create_draft_form_data, follow=True) # Important to follow to see final page
        self.assertEqual(response.status_code, 200)
        # A success message might not be directly on this page if it redirects to an edit view.
        # However, the action of creating a new draft should have occurred.

        # 4. Assert the Outcome
        all_versions = Version.objects.filter_by_grouper(grouper).order_by('-created')
        self.assertEqual(all_versions.count(), 2,
                         "Should be two versions: the original published and the new draft.")

        new_draft_version = all_versions.first() # Newest should be the new draft
        original_published_version_after_action = all_versions.last() # Oldest should be the published one

        self.assertEqual(new_draft_version.state, DRAFT, "The new version should be a DRAFT.")
        self.assertEqual(new_draft_version.created_by, self.admin_user,
                         "New draft should be created by the logged-in admin user.")

        new_draft_content = new_draft_version.content
        self.assertIsNotNone(new_draft_content, "New draft version should have content.")
        self.assertNotEqual(new_draft_content.pk, published_content.pk,
                            "New draft content should be a new ArticleContent instance.")

        # Verify content was copied
        # Need to fetch translations for comparison
        published_content.set_current_language(self.language)
        new_draft_content.set_current_language(self.language)
        self.assertEqual(new_draft_content.title, published_content.title, "Title should be copied to the new draft.")
        self.assertEqual(new_draft_content.article_grouper, published_content.article_grouper)

        # Ensure the original published version is still PUBLISHED
        self.assertEqual(original_published_version_after_action.state, PUBLISHED,
                         "Original version should remain PUBLISHED.")
        self.assertEqual(original_published_version_after_action.pk, published_version.pk,
                         "The older version should be the one we initially published.")

    def test_unpublish_article_via_admin(self):
        """
        Tests unpublishing a published article via an admin action.
        """
        # 1. Create and publish an article programmatically
        unpublish_title = "Article for Unpublishing Test"
        # Ensure Person object exists for self.admin_user for create_article helper
        Person.objects.get_or_create(user=self.admin_user, defaults={'name': self.admin_user.get_full_name() or "Admin Test Person Unpublish"})

        draft_content = self.create_article(
            title=unpublish_title,
            owner=self.admin_user,
            author=Person.objects.get(user=self.admin_user)
        )
        grouper = draft_content.article_grouper
        version_to_publish = Version.objects.get_for_content(draft_content)

        # Publish it using the versioning API
        published_version = versioning_api.publish(version_to_publish, self.admin_user)
        published_version.refresh_from_db() # Ensure state is updated from the publish call
        self.assertEqual(published_version.state, PUBLISHED)

        # 2. Get the ArticleGrouper change view URL
        grouper_change_url = reverse('admin:aldryn_newsblog_articlegrouper_change', args=[grouper.pk])

        # 3. Simulate the "Unpublish" Action
        # This action in djangocms-versioning is typically named 'unpublish'.
        unpublish_form_data = {
            'unpublish': 'Unpublish', # This is an assumption for the action name and value
        }

        response = self.client.post(grouper_change_url, data=unpublish_form_data, follow=True)
        self.assertEqual(response.status_code, 200, f"Unpublish POST request failed. Errors: {response.context.get('errors') if response.context else 'No context'}")
        # Check for a success message (these can be fragile but good for confirmation)
        # Example message: "The version was unpublished successfully." - adjust as per actual message
        self.assertContains(response, "unpublished successfully",
                            msg_prefix="Success message for unpublish not found.")

        # 4. Assert the Outcome
        published_version.refresh_from_db() # Refresh to get the latest state after the admin action
        # djangocms-versioning typically sets the state to ARCHIVED upon unpublishing.
        self.assertEqual(published_version.state, ARCHIVED,
                         "Article version state did not change to ARCHIVED after unpublish.")

        # Ensure it's still the same version object, just state changed.
        self.assertEqual(Version.objects.filter_by_content(draft_content).count(), 1)
        self.assertEqual(Version.objects.get_for_content(draft_content).pk, published_version.pk)

    def test_revert_to_previous_version_via_admin(self):
        """
        Tests reverting to a previous version of an article via the admin interface.
        This should create a new draft based on the content of the reverted version.
        """
        # 1. Create and publish V1
        v1_title = "Revert Test V1 Title"
        v1_lead_in = "Content V1 LeadIn"
        # Ensure Person object exists for self.admin_user
        Person.objects.get_or_create(user=self.admin_user, defaults={'name': self.admin_user.get_full_name() or "Admin Test Person Revert"})

        v1_draft_content = self.create_article(
            title=v1_title,
            lead_in=v1_lead_in,
            owner=self.admin_user,
            author=Person.objects.get(user=self.admin_user)
        )
        grouper = v1_draft_content.article_grouper
        v1_initial_version = Version.objects.get_for_content(v1_draft_content)
        v1_published_version = versioning_api.publish(v1_initial_version, self.admin_user)
        # v1_published_version.content is v1_draft_content

        # 2. Create and publish V2 (a modification of V1)
        v2_title = "Revert Test V2 Title"
        v2_lead_in = "Content V2 LeadIn"
        v2_draft_for_publish = versioning_api.create_draft(v1_published_version, self.admin_user)
        v2_draft_content_for_publish = v2_draft_for_publish.content
        v2_draft_content_for_publish.title = v2_title
        v2_draft_content_for_publish.lead_in = v2_lead_in
        v2_draft_content_for_publish.save()
        v2_published_version = versioning_api.publish(v2_draft_for_publish, self.admin_user)
        # v2_published_version.content is v2_draft_content_for_publish

        # At this point:
        # v1_published_version is ARCHIVED (or the state djangocms-versioning puts old published versions in)
        # v2_published_version is PUBLISHED

        v1_published_version.refresh_from_db() # get its updated state after v2 was published
        self.assertEqual(v1_published_version.state, ARCHIVED, "V1 should be ARCHIVED after V2 is published.")
        self.assertEqual(v2_published_version.state, PUBLISHED, "V2 should be PUBLISHED.")

        # 3. Find and Simulate the "Revert" Action for V1
        # The revert URL is typically associated with the content model's admin, not the grouper.
        # It usually takes the PK of the version to revert.
        revert_url_name = f'admin:{ArticleContent._meta.app_label}_{ArticleContent._meta.model_name}_revert'
        try:
            # We are reverting to v1_published_version (which is now ARCHIVED)
            revert_url = reverse(revert_url_name, args=[v1_published_version.pk])
        except NoReverseMatch:
            self.fail(f"Could not resolve revert URL named '{revert_url_name}'. Check djangocms-versioning URL patterns.")

        # The revert view usually presents a confirmation page (GET), then performs action on POST.
        # First, let's GET the confirmation page.
        get_revert_page_response = self.client.get(revert_url)
        self.assertEqual(get_revert_page_response.status_code, 200, "Failed to GET revert confirmation page.")
        self.assertContains(get_revert_page_response, "Are you sure you want to revert to this version?",
                            msg_prefix="Revert confirmation page content not as expected.")

        # Now, POST to confirm the revert action.
        # No specific form data is usually needed for the revert POST itself, other than CSRF.
        revert_action_response = self.client.post(revert_url, follow=True) # follow=True to get the final page after redirect
        self.assertEqual(revert_action_response.status_code, 200, "POST to revert URL failed.")
        # Successful revert usually redirects to the changelist of the grouper or the edit view of the new draft.
        # Check for a success message.
        self.assertContains(revert_action_response, "The new draft based on the reverted version has been successfully created.",
                            msg_prefix="Success message for revert not found.")


        # 4. Assert the Outcome
        all_versions = Version.objects.filter_by_grouper(grouper).order_by('-created')
        # Expected: V1 (Archived), V2 (Published), New Draft from V1 content (Draft)
        self.assertEqual(all_versions.count(), 3, "Should be three versions after revert.")

        new_reverted_draft_version = all_versions.first() # Newest is the new draft
        self.assertEqual(new_reverted_draft_version.state, DRAFT, "The newest version should be a DRAFT.")
        self.assertEqual(new_reverted_draft_version.created_by, self.admin_user,
                         "New draft from revert should be created by the logged-in admin user.")

        reverted_draft_content = new_reverted_draft_version.content
        self.assertIsNotNone(reverted_draft_content, "New draft from revert should have content.")
        # The new draft content PK should be different from V1's original draft content PK
        # and also different from V2's content PK.
        self.assertNotEqual(reverted_draft_content.pk, v1_draft_content.pk)
        self.assertNotEqual(reverted_draft_content.pk, v2_published_version.content.pk)

        # Verify content was copied from V1
        # Set language context for Parler fields
        v1_draft_content.set_current_language(self.language) # Original V1 content
        reverted_draft_content.set_current_language(self.language)
        self.assertEqual(reverted_draft_content.title, v1_draft_content.title,
                         "Title of new draft should match V1's title.")
        self.assertEqual(reverted_draft_content.lead_in, v1_draft_content.lead_in,
                         "Lead-in of new draft should match V1's lead-in.")
        self.assertEqual(reverted_draft_content.article_grouper, grouper)

        # V2 should still be the currently published version
        v2_published_version.refresh_from_db()
        self.assertEqual(v2_published_version.state, PUBLISHED, "V2 should remain PUBLISHED after V1 revert.")

        # V1 (the version we reverted to) should still be ARCHIVED
        v1_published_version.refresh_from_db()
        self.assertEqual(v1_published_version.state, ARCHIVED, "V1 (reverted from) should remain ARCHIVED.")
