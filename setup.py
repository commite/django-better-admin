#!/usr/bin/env python
from distutils.core import setup

# Dynamically calculate the version based on modeltranslation.VERSION.

VERSION = (0, 0, 1, 'alpha', 1)


def get_version():
    """
    Returns a PEP 386-compliant version number from VERSION.
    """
    version = VERSION

    assert len(version) == 5
    assert version[3] in ('alpha', 'beta', 'rc', 'final')

    # Now build the two parts of the version number:
    # main = X.Y[.Z]
    # sub = .devN - for pre-alpha releases
    #     | {a|b|c}N - for alpha, beta and rc releases

    parts = 2 if version[2] == 0 else 3
    main = '.'.join(str(x) for x in version[:parts])

    sub = ''
    if version[3] == 'alpha' and version[4] == 0:
        git_changeset = get_git_changeset()
        if git_changeset:
            sub = '.dev%s' % git_changeset

    elif version[3] != 'final':
        mapping = {'alpha': 'a', 'beta': 'b', 'rc': 'rc'}
        sub = mapping[version[3]] + str(version[4])

    return str(main + sub)

version = get_version()

setup(
    name='django-better-admin',
    version=version,
    description='.',
    long_description=(
        '''
        Long Description
        '''),
    author='Commite',
    author_email='peschler@commite.com',
    url='https://github.com/commite/django-better-admin',
    packages=['betteradmin', ],
    package_data={'betteradmin': [
        'static/betteradmin/css/*.css',
        'static/betteradmin/js/*.js']},
    requires=['django(>=1.9)'],
    download_url='https://github.com/commite/django-better-admin/archive/%s.tar.gz' % version,
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Operating System :: OS Independent',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Framework :: Django',
        ],
    license='Apache 2.0')

