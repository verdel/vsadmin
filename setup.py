#!/usr/bin/env python
# -*- coding: utf-8 -*-

from codecs import open
from os import path
from setuptools import setup, find_packages

here = path.abspath(path.dirname(__file__))

# Parse the version from the mapbox module.
with open('ipamcli/__init__.py') as f:
    for line in f:
        if line.find("__version__") >= 0:
            version = line.split("=")[1].strip()
            version = version.strip('"')
            version = version.strip("'")
            continue

with open(path.join(here, 'README.rst'), encoding='utf-8') as readme_file:
    readme = readme_file.read()

with open(path.join(here, 'HISTORY.rst'), encoding='utf-8') as history_file:
    history = history_file.read().replace('.. :changelog:', '')

requirements = [
    'pyvmomi',
    'click'
]

setup(
    name='vsadmin',
    version=version,
    description='Command line interface to Vmware vSphere.',
    long_description=readme + '\n\n' + history,
    author='Vadim Aleksandrov',
    author_email='valeksandrov@me.com',
    url='https://github.com/verdel/vsadmin',
    test_suite='tests',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    entry_points={'console_scripts': ['vsadmin=vsadmin.cli:cli', ], },
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        'test': ['responses'],
    },
    keywords='vsadmin',
    license="MIT",
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5'
    ]
)
