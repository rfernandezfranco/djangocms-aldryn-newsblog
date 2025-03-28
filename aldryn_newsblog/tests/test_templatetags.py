from django.test import SimpleTestCase

from aldryn_newsblog.templatetags.aldryn_newsblog import (
    prepend_prefix_if_exists,
)


class PrependPrefixIfExistsTest(SimpleTestCase):

    def test_no_context(self):
        self.assertEqual(prepend_prefix_if_exists({}, "path/page.html"), "aldryn_newsblog/path/page.html")

    def test_no_template(self):
        self.assertEqual(prepend_prefix_if_exists({
            "aldryn_newsblog_template_prefix": "custom"
        }, "path/page.html"), "aldryn_newsblog/path/page.html")

    def test_dummy_template(self):
        self.assertEqual(prepend_prefix_if_exists({
            "aldryn_newsblog_template_prefix": "dummy"
        }, "article_detail.html"), "aldryn_newsblog/dummy/article_detail.html")

    def test_more_dummy_template(self):
        self.assertEqual(prepend_prefix_if_exists({
            "aldryn_newsblog_template_prefix": "dummy"
        }, "article_detail.html"), "aldryn_newsblog/dummy/article_detail.html")
        # Run again does not call function get_template.
        self.assertEqual(prepend_prefix_if_exists({
            "aldryn_newsblog_template_prefix": "dummy"
        }, "article_detail.html"), "aldryn_newsblog/dummy/article_detail.html")
