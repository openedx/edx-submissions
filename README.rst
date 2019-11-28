Part of `edX code`__.

__ http://code.edx.org/

.. image:: https://travis-ci.org/edx/edx-submissions.png?branch=master
    :alt: Travis build status

.. image:: https://coveralls.io/repos/edx/edx-submissions/badge.png?branch=master
    :target: https://coveralls.io/r/edx/edx-submissions?branch=master
    :alt: Coverage badge


edx-submissions
===============

API for creating submissions and scores.


Overview
--------

``submissions`` is a Django app that defines a common interface for creating submissions and scores.


Getting Started
---------------

To install the ``submissions`` app:

.. code:: bash

    python setup.py install


To run the test suite:

.. code:: bash

    make test_requirements
    tox # to run only a single environment, do e.g. tox -e py35-django22-drf39


To use a Django shell to test commands:

.. code:: bash

    make dev_requirements
    ./manage.py migrate
    ./manage.py shell --settings=settings
    >>> from submissions.serializers import StudentItemSerializer
    >>> <other commands...>

License
-------

The code in this repository is licensed under version 3 of the AGPL unless
otherwise noted.

Please see ``LICENSE.txt`` for details.


How To Contribute
-----------------

Contributions are very welcome.

Please read `How To Contribute <https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst>`_ for details.

Even though it was written with ``edx-platform`` in mind, the guidelines
should be followed for Open edX code in general.


Reporting Security Issues
-------------------------

Please do not report security issues in public. Please email security@edx.org


Mailing List and IRC Channel
----------------------------

You can discuss this code on the `edx-code Google Group`__ or in the
``edx-code`` IRC channel on Freenode.

__ https://groups.google.com/forum/#!forum/edx-code
