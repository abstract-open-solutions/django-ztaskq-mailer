from setuptools import setup, find_packages
import os


version = '1.0'


setup(
    name='django-ztaskq-mailer',
    version=version,
    description="An asyncronous Django mail backend using django_ztaskq",
    long_description=open("README.rst").read() + "\n" +
                     open(os.path.join("docs", "HISTORY.rst")).read(),
    classifiers=[
        "Programming Language :: Python",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License"
    ],
    keywords='django mail asyncronous backend zeromq zmq',
    author='Simone Deponti',
    author_email='simone.deponti@abstract.it',
    url='http://github.com/abstract-open-solutions/django-ztaskq-mailer/',
    license='BSD',
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'setuptools',
        'Django',
        'django_ztaskq>=0.3.0',
        'mock'
    ]
)
