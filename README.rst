=============================================
devpi-pr: push request index plugin for devpi
=============================================

This plugin adds a *push request* workflow to `devpi-server`_ and supporting commands to `devpi-client`.

.. _devpi-server: http://pypi.python.org/pypi/devpi-server
.. _devpi-client: http://pypi.python.org/pypi/devpi-client


Installation
============

``devpi-pr`` needs to be installed alongside ``devpi-server`` to enable *push request* functionality.

On client machines it is optional,
but highly recommended to be installed alongside ``devpi-client`` to have more convenient options to manage *push requests*.

You can install it with::

    pip install devpi-pr

There is no configuration needed as ``devpi-server`` and ``devpi-client`` will automatically discover the plugin through calling hooks using the setuptools entry points mechanism.


Motivation
==========

Many Python projects have complex dependencies and are often split into separate packages.
For such projects it's often not feasible to upload, review, test and release singular packages.

To allow a workflow that covers more than one package,
this plugin introduces the concept of a special *merge index*.

That new *merge index* allows to push several packages in one go into another index.
It allows to view the test results of all these packages in one central location.
Additionally it has associated workflow states which allow to establish further workflow restrictions.

Another motivation is the ability for users with no write access to an index to create *push requests* which are then handled by users with write access.


Usage
=====

Creating a push request
-----------------------

With devpi-client new-pr command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``devpi-pr`` plugin adds new commands when installed alongside ``devpi-client``.

Lets say the currently used index has packages ``pkg-app 1.0`` and ``app-dependency 1.2``.
To create a new *push request* with packages from the currently selected index to the target index ``prod/main`` the following command is used:

.. code-block:: bash

    $ devpi new-pr 20180322 prod/main pkg-app==1.0 app-dependency==1.2

This creates a new *merge index* named ``20180322`` and adds the two packages from the current index to it.

It's possible to upload and push further packages at this point.

Afterwards it can be submitted like this:

.. code-block:: bash

    $ devpi submit-pr 20180322

When the EDITOR environment variable is set it is used to open an editor to provide a message for the *push request*,
otherwise a simple prompt is used.
Optionally the message can be added directly to the *push request* with the ``-m`` option of the ``submit-pr`` command.

The state of the *merge index* is now set to ``pending``.


Manually in separate steps
~~~~~~~~~~~~~~~~~~~~~~~~~~

It's also possible to create a *push request* manually.
This works without ``devpi-pr`` installed alongside ``devpi-client``,
but is more complex.

First a new *merge index* needs to be created.
The index name must be of type ``merge`` and the target index specified in ``bases``:

.. code-block:: bash

    $ devpi index -c 20180322 type=merge bases=prod/main

Once the index is created, packages can be uploaded to it with ``devpi upload`` or pushed from another index with ``devpi push``.

At last the ``state`` of the index needs to be changed to ``pending`` and a state change message be added:

.. code-block:: bash

    $ devpi index 20180322 state=pending messages+="Please approve these updated packages"


Managing push requests
----------------------

This requires the ``devpi-pr`` plugin on the client side.

The ``devpi-pr`` plugin adds the new commands ``new-pr``, ``approve-pr``, ``delete-pr``, ``list-prs``, ``reject-pr`` and ``submit-pr`` when installed alongside ``devpi-client``.

If the target index has the ``push_requests_allowed`` option set to ``True``,
then all users in ``acl_upload`` can manage incoming *push requests*,
otherwise an error is returned.

All commands which change the state of a *push request* ask for a message and accept the ``-m`` option to provide it directly.

To list all pending *push requests* for a target index,
use the ``list-prs`` command with the name of the target index:

.. code-block:: bash

    $ devpi list-prs prod/main
    user/20180322 10

With info about release files:

.. code-block:: bash

    $ devpi list-prs -v prod/main
    user/20180322 10
        app-dependency 1.2
            app-dependency-1.2.tgz sha256=924ad82c...
        pkg-app 1.0
            pkg-app-1.0.tgz sha256=02af923e...

With tox (test) result infos:

.. code-block:: bash

    $ devpi list-prs -vt prod/main
    user/20180322 10 (differing tox results)
        app-dependency 1.2 (all tests passed)
            app-dependency-1.2.tgz sha256=924ad82c...
        pkg-app 1.0 (no tox results)
            pkg-app-1.0.tgz sha256=02af923e...

The ``10`` after the name is the current serial number needed for other commands to avoid surprises when something changed in the meantime.

To approve or reject a *push request* use ``approve-pr`` and ``reject-pr``:

.. code-block:: bash

    $ devpi approve-pr user/20180322 10
    The push request user/20180322 was approved and the following packages from it pushed into prod/main:
    app-dependency 1.2
        app-dependency-1.2.tgz sha256=924ad82c...
    pkg-app 1.0
        pkg-app-1.0.tgz sha256=02af923e...


An example where the *push request* has changed:

.. code-block:: bash

    $ devpi reject-pr user/20180322 10 -m "The test results for pkg-app are missing"
    The push request has changed since serial 10. Please inspect it again.
