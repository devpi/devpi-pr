====================================================
devpi-pr: push request index plugin for devpi-server
====================================================

This plugin adds a push request workflow to `devpi-server`_.

.. _devpi-server: http://pypi.python.org/pypi/devpi-server


Installation
============

``devpi-pr`` needs to be installed alongside ``devpi-server`` and optionally ``devpi-client``.

You can install it with::

    pip install devpi-pr

There is no configuration needed as ``devpi-server`` and ``devpi-client`` will automatically discover the plugin through calling hooks using the setuptools entry points mechanism.


Motivation
==========

Many Python projects have complex dependencies and are often split into separate packages.
For such projects it's often not feasible to upload, review, test and release singular packages.

To allow a workflow that covers more than one package, this plugin introduces the concept of a special *merge* index.

That new *merge* index allows to push several packages in one go into another index.
It allows to view the test results of all these packages in one central location.
Additionally it has associated workflow states which allow to establish further workflow restrictions.


Usage
=====

Creating a push request
-----------------------

With devpi-client pr command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``devpi-pr`` plugin adds a new ``pr`` command when installed alongside ``devpi-client``.

Lets say the currently used index has packages ``pkg-app 1.0`` and ``app-dependency 1.2``.
To create a new *push request* with packages from the currently selected index to the target index ``prod/main``, the following command is used:

.. code-block::

    $ devpi pr pkg-app==1.0 app-dependency==1.2 prod/main

When the EDITOR environment variable is set, it is used to open an editor to provide a message for the *push request*, otherwise a simple prompt is used.
Optionally the message can be added directly to the *push request* with the ``-m`` option of the ``pr`` command.

A new index with a unique name prefixed by ``+pr-`` of type ``merge`` is created, the packages ``pkg-app 1.0`` and ``app-dependency 1.2`` are pushed to it and the state is set to ``pending``.


Manually in separate steps
~~~~~~~~~~~~~~~~~~~~~~~~~~

It's also possible to create a *push request* manually.
This allows more fine grained control over the process and works without ``devpi-pr`` installed alongside ``devpi-client``.

First a new *merge* index needs to be created. The index name must start with ``+pr-``, be of type ``merge`` and the target index specified in ``bases``:

.. code-block::

    $ devpi index -c +pr-20180322 type=merge bases=prod/main

Once the index is created, packages can be uploaded to it with ``devpi upload`` or pushed from another index with ``devpi push``.

At last the ``state`` of the index needs to be changed to ``pending``:

.. code-block::

    $ devpi index +pr-20180322 state=pending


Managing push requests
----------------------

With new devpi-client commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``devpi-pr`` plugin adds the new commands ``accept-pr``, ``delete-pr``, ``list-prs``, ``reject-pr`` and ``submit-pr`` when installed alongside ``devpi-client``.

If the target index has the ``push_requests_allowed`` option set to ``True``, then all users in ``acl_upload`` can manage incoming *push requests*, otherwise an error is returned.

All commands which change the state of a *push request* ask for a message and accept the ``-m`` option to provide it directly.

To list all pending *push requests* the ``list-prs`` command is used with the name of the target index:

.. code-block::

    $ devpi list-prs prod/main
    user/+pr-20180322 10

With info about release files:

.. code-block::

    $ devpi list-prs -v prod/main
    user/+pr-20180322 10
        app-dependency 1.2
            app-dependency-1.2.tgz sha256=924ad82c...
        pkg-app 1.0
            pkg-app-1.0.tgz sha256=02af923e...

With tox (test) result infos:

.. code-block::

    $ devpi list-prs -vt prod/main
    user/+pr-20180322 10 (differing tox results)
        app-dependency 1.2 (all tests passed)
            app-dependency-1.2.tgz sha256=924ad82c...
        pkg-app 1.0 (no tox results)
            pkg-app-1.0.tgz sha256=02af923e...

The ``10`` after the name is the current serial number needed for other commands to avoid surprises when something changed in the meantime.

To accept or reject a *push request*, use ``accept-pr`` and ``reject-pr``:

.. code-block::

    $ devpi accept-pr user/+pr-20180322 10
    The push request user/+pr-20180322 was accepted and the following packages from it pushed into prod/main:
    app-dependency 1.2
        app-dependency-1.2.tgz sha256=924ad82c...
    pkg-app 1.0
        pkg-app-1.0.tgz sha256=02af923e...


An example where the *push request* has changed:

.. code-block::

    $ devpi reject-pr user/+pr-20180322 10 -m "The test results for pkg-app are missing"
    The push request has changed since serial 10. Please inspect it again.

