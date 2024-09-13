edx-submissions
###############

|pypi-badge| |ci-badge| |codecov-badge| |doc-badge| |pyversions-badge| |license-badge| |status-badge|


Purpose
*******

``submissions`` is a Django app that defines a common interface for creating submissions and scores.

Getting Started with Development
********************************

To install the ``submissions`` app, run these commands from the `edx-submissions` root directory:

.. code:: bash

    pip install -e


To run the test suite:

.. code:: bash

    pip install tox
    tox # to run only a single environment, do e.g. tox -e py312-django42-drflatest


To use a Django shell to test commands:

.. code:: bash

    make dev_requirements
    python manage.py migrate
    python manage.py shell --settings=settings
    >>> from submissions.serializers import StudentItemSerializer
    >>> <other commands...>

Deploying
*********

Tagged versions of the edx-submissions library are released to pypi.org.

To use the latest release in your project, add the following to your pip requirements file:

.. code:: bash

    edx-submissions

Getting Help
************

Documentation
=============

Start by going through `the documentation`_ (generated from `/docs </docs/source/index.rst>`_).  If you need more help see below.

.. _the documentation: https://docs.openedx.org/projects/edx-submissions

More Help
=========

If you're having trouble, we have discussion forums at
https://discuss.openedx.org where you can connect with others in the
community.

Our real-time conversations are on Slack. You can request a `Slack
invitation`_, then join our `community Slack workspace`_.

For anything non-trivial, the best path is to open an issue in this
repository with as many details about the issue you are facing as you
can provide.

https://github.com/openedx/edx-submissions/issues

For more information about these options, see the `Getting Help <https://openedx.org/getting-help>`__ page.

.. _Slack invitation: https://openedx.org/slack
.. _community Slack workspace: https://openedx.slack.com/

License
*******

The code in this repository is licensed under version 3 of the AGPL unless
otherwise noted.

Please see `LICENSE.txt <LICENSE.txt>`_ for details.

Contributing
************

Contributions are very welcome.
Please read `How To Contribute <https://openedx.org/r/how-to-contribute>`_ for details.

This project is currently accepting all types of contributions, bug fixes,
security fixes, maintenance work, or new features.  However, please make sure
to have a discussion about your new feature idea with the maintainers prior to
beginning development to maximize the chances of your change being accepted.
You can start a conversation by creating a new issue on this repo summarizing
your idea.

The Open edX Code of Conduct
****************************

All community members are expected to follow the `Open edX Code of Conduct`_.

.. _Open edX Code of Conduct: https://openedx.org/code-of-conduct/

People
******

The assigned maintainers for this component and other project details may be
found in `Backstage`_. Backstage pulls this data from the ``catalog-info.yaml``
file in this repo.

.. _Backstage: https://backstage.openedx.org/catalog/default/component/edx-submissions

Reporting Security Issues
*************************

Please do not report security issues in public. Please email security@openedx.org.

.. |pypi-badge| image:: https://img.shields.io/pypi/v/edx-submissions.svg
    :target: https://pypi.python.org/pypi/edx-submissions/
    :alt: PyPI

.. |ci-badge| image:: https://github.com/openedx/edx-submissions/actions/workflows/ci.yml/badge.svg?branch=master
    :target: https://github.com/openedx/edx-submissions/actions/workflows/ci.yml?branch=master
    :alt: CI

.. |codecov-badge| image:: https://codecov.io/github/openedx/edx-submissions/coverage.svg?branch=master
    :target: https://codecov.io/github/openedx/edx-submissions?branch=master
    :alt: Codecov

.. |doc-badge| image:: https://readthedocs.org/projects/edx-submissions/badge/?version=latest
    :target: https://docs.openedx.org/projects/edx-submissions
    :alt: Documentation

.. |pyversions-badge| image:: https://img.shields.io/pypi/pyversions/edx-submissions.svg
    :target: https://pypi.python.org/pypi/edx-submissions/
    :alt: Supported Python versions

.. |license-badge| image:: https://img.shields.io/github/license/openedx/edx-submissions.svg
    :target: https://github.com/openedx/edx-submissions/blob/master/LICENSE.txt
    :alt: License

.. .. |status-badge| image:: https://img.shields.io/badge/Status-Experimental-yellow
.. |status-badge| image:: https://img.shields.io/badge/Status-Maintained-brightgreen
.. .. |status-badge| image:: https://img.shields.io/badge/Status-Deprecated-orange
.. .. |status-badge| image:: https://img.shields.io/badge/Status-Unsupported-red
