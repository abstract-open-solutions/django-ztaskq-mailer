django_ztaskq_mailer
====================

A Django_ mail backend that uses `django_ztaskq`_ to queue mails
and send them asyncronously.

Usage
-----

Install the package via pip_::

    $ pip install django-ztaskq-mailer

or via distribute_, in case you are using a development version
or a source code checkout::

    $ python setup.py install

Then add it to the list of installed applications::

    INSTALLED_APPS = (
        ...
        'django_ztaskq_mailer',
    )

And then you can specify the email backend::

    EMAIL_BACKEND = 'django_ztaskq_mailer.backend.EmailBackend'


.. _Django: http://www.djangoproject.com/
.. _`django_ztaskq`: https://github.com/awesomo/django_ztaskq
.. _pip: http://www.pip-installer.org/en/latest/index.html
.. _distribute: http://pypi.python.org/pypi/distribute/
