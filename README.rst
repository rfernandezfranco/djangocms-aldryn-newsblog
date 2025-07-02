|Project continuation| |Pypi package| |Pypi status| |Python versions| |License|


Aldryn News & Blog for django CMS
=================================

Continuation of the deprecated project `Divio Aldryn News&Blog <https://github.com/divio/aldryn-newsblog>`_.

Aldryn News & Blog is an `Aldryn <http://aldryn.com>`_-compatible news and
weblog application for `django CMS <http://django-cms.org>`_.

**Content editors** looking for documentation on how to use the editing
interface should refer to our `user manual`_ section.

**Django developers** who want to learn more about django CMS, as well as
how to install, configure and customize it for their own projects should
refer to the `documentation`_ sections.

Aldryn News & Blog is intended to serve as a model of good practice for
development of django CMS and Aldryn applications.

.. _user manual: http://aldryn-newsblog.readthedocs.io/en/latest/


======================
Installation & Updates
======================

Please head over to our `documentation`_ for all the details on how to install,
configure and use Aldryn News & Blog.

You can also find instructions on `how to upgrade`_ from earlier versions.

.. _documentation: http://aldryn-newsblog.readthedocs.io/en/latest/
.. _how to upgrade: http://aldryn-newsblog.readthedocs.io/en/latest/upgrade.html


============
Contributing
============

This is a an open-source project. We'll be delighted to receive your
feedback in the form of issues and pull requests. Before submitting your
pull request, please review our `contribution guidelines
<http://docs.django-cms.org/en/latest/contributing/index.html>`_.

We're grateful to all contributors who have helped create and maintain this package.
Contributors are listed at the `contributors <https://github.com/divio/aldryn-newsblog/graphs/contributors>`_
section.


.. |Project continuation| image:: https://img.shields.io/badge/Continuation-Divio_Aldryn_News&Blog-blue
    :target: https://github.com/CZ-NIC/djangocms-aldryn-newsblog
    :alt: Continuation of the deprecated project "Divio Aldryn News&Blog"
.. |Pypi package| image:: https://img.shields.io/pypi/v/djangocms-aldryn-newsblog.svg
    :target: https://pypi.python.org/pypi/djangocms-aldryn-newsblog/
    :alt: Pypi package
.. |Pypi status| image:: https://img.shields.io/pypi/status/djangocms-aldryn-newsblog.svg
   :target: https://pypi.python.org/pypi/djangocms-aldryn-newsblog
   :alt: status
.. |Python versions| image:: https://img.shields.io/pypi/pyversions/djangocms-aldryn-newsblog.svg
   :target: https://pypi.python.org/pypi/djangocms-aldryn-newsblog
   :alt: Python versions
.. |License| image:: https://img.shields.io/pypi/l/djangocms-aldryn-newsblog.svg
    :target: https://pypi.python.org/pypi/djangocms-aldryn-newsblog/
    :alt: license


====================
Versioning Support
====================

This plugin supports `djangocms-versioning <https://github.com/django-cms/djangocms-versioning>`_
for version control over articles. This is an optional but highly recommended feature.

To enable versioning:

1.  **Install djangocms-versioning:**
    Make sure `djangocms-versioning` and its dependencies (like `djangocms-versions`)
    are installed in your Django project environment.
    You can typically install it using pip:

    .. code-block:: bash

        pip install djangocms-versioning

    This plugin has been primarily tested with ``djangocms-versioning==2.3.2``.
    Newer versions might also work but may require adjustments.

2.  **Integration Details:**
    *   The `ArticleContent` model (which holds the main content of an article like title,
        lead-in, and placeholders) is registered for versioning.
    *   Each `ArticleContent` is linked to an `ArticleGrouper` model, which acts as the
        stable "master" record for an article across its different versions.
    *   When `djangocms-versioning` is active, publishing and unpublishing of articles
        are handled through its mechanisms, providing a full audit trail and the ability
        to revert to previous versions.

If `djangocms-versioning` is not installed, the plugin will operate without these
versioning capabilities, using its traditional (non-versioned) mode. The admin
interface and behavior will adapt accordingly.


## Testing

Run `pip install -e .[testing]` and `pip install -r test_requirements.txt` before
executing `python custom_manage.py test`. These requirements install
``djangocms-versioning`` so imports like ``VersionableItem`` resolve correctly.
Without this package Django fails to start with an ``ImportError`` about
``VersionableItem``.

