# -*- coding: utf-8 -*-
from setuptools import find_packages, setup

from aldryn_newsblog import __version__


REQUIREMENTS = [
    'Django>=2.2.13,<4',
    'django-cms>=3.7.3<4.0.0',
    'python-dateutil>==2.8.1<3.0.0',
    'aldryn-apphooks-config>=0.6.0<1.0.0',
    'aldryn-boilerplates>=0.8.0<1.0.0',
    'aldryn-categories>=1.2.0<2.0.0',
    'aldryn-common>=1.0.5<2.0.0',
    'aldryn-people>=2.2.0<3.0.0',
    'aldryn-translation-tools @ git+https://github.com/zbohm/aldryn-translation-tools.git@update-to-django2',
    'backport-collections>=0.1<1.0.0',
    'django-appdata>==0.3.0<1.0.0',
    'djangocms-text-ckeditor>=3.9.1<4.0.0',
    'django-filer @ git+https://github.com/zbohm/django-filer@fix-on_delete',
    'django-parler>=2.0.1<3.0.0',
    'django-sortedm2m>=3.0.0<4.0.0',
    'django-taggit>=1.3.0<2.0.0',
    'lxml>=4.5.1<5.0.0',
    'six>=1.15.0<2.0.0',
]

# https://pypi.python.org/pypi?%3Aaction=list_classifiers
CLASSIFIERS = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: Web Environment',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Framework :: Django',
    'Framework :: Django :: 1.11',
    'Framework :: Django :: 2.0',
    'Framework :: Django :: 2.1',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Topic :: Internet :: WWW/HTTP',
    'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: News/Diary',
    'Topic :: Software Development',
    'Topic :: Software Development :: Libraries',
    'Topic :: Software Development :: Libraries :: Application Frameworks',
]

setup(
    name='aldryn-newsblog',
    version=__version__,
    author='Divio AG',
    author_email='info@divio.ch',
    url='https://github.com/aldryn/aldryn-newsblog',
    license='BSD',
    description='Adds blogging and newsing capabilities to django CMS',
    long_description=open('README.rst').read(),
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=REQUIREMENTS,
    classifiers=CLASSIFIERS,
    test_suite="test_settings.run",
)
