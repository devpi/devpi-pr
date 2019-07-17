devpi-pr: pull request plugin for devpi
=======================================

This plugin adds a *pull request* workflow to `devpi-server`_ and supporting commands to `devpi-client`_.

.. _devpi-server: http://pypi.python.org/pypi/devpi-server
.. _devpi-client: http://pypi.python.org/pypi/devpi-client


Installation
------------

``devpi-pr`` needs to be installed alongside ``devpi-server`` to enable *pull request* functionality.

On client machines the creation and submission of *pull requests* is possible without the plugin, but more convenient with it installed.
All other functionality requires the ``devpi-pr`` plugin to be installed alongside ``devpi-client``.

You can install it with::

    pip install devpi-pr

There is no configuration needed as ``devpi-server`` and ``devpi-client`` will automatically discover the plugin through calling hooks using the setuptools entry points mechanism.


Motivation
----------

Many Python projects have complex dependencies and are often split into separate packages.

For such projects it would be advantageous to handle a set of packages as a single unit.

In organizations an authenticated flow of package releases is often required.

This plugin introduces the concept of a *pull request* to help with all that.

The result of a successful *pull request* is a single atomic update of packages in the target index.


Usage
-----

The ``devpi-pr`` plugin adds new commands when installed alongside ``devpi-client``.

``new-pr``
    Create a new pull request.

``submit-pr``
    Submit an existing pull request for review.

``list-prs``
    List pull requests.

``review-pr``
    Start reviewing a submitted pull request.

``abort-pr-review``
    Abort review of pull request.

``approve-pr``
    Approve reviewed pull request.

``reject-pr``
    Reject pull request.

``cancel-pr``
    Cancel ``submitted`` state of pull request by submitter.

``delete-pr``
    Completely remove a pull request including any uploaded packages.


In ``devpi-server`` a *pull request* is represented by a special *pr index*.
It behaves mostly like a regular index with some additional restrictions and behaviors.

All commands which change the state of a *pull request* ask for a message and accept the ``-m`` option to provide it directly.
When the ``EDITOR`` environment variable is set it is used to open an editor to provide a message,
otherwise a simple prompt is used.


Creating a pull request
~~~~~~~~~~~~~~~~~~~~~~~

Lets say a new feature is created which requires changes in multiple packages.
We are currently working on a development index ``user/dev`` where we have two changed packages ``pkg-app 1.0`` and ``app-dependency 1.2``.
The target index where the packages should end up for production is named ``prod/main``.

The ``pull_requests_allowed`` option of the target index must be ``True``:

.. code-block:: bash

    $ devpi index prod/main
    http://example.com/prod/main:
      type=stage
      bases=root/pypi
      volatile=True
      acl_upload=root
      acl_toxresult_upload=:ANONYMOUS:
      mirror_whitelist=
      pull_requests_allowed=True

We first create a new *pull request* for the target:

.. code-block:: bash

    $ devpi new-pr new-feature prod/main

This creates a new *pr index* named ``user/new-feature``.

Next we push the existing packages from our development index into the *pr index*.

.. code-block:: bash

    $ devpi push pkg-app==1.0 user/new-feature
    $ devpi push app-dependency==1.2 user/new-feature

As the *pr index* is mostly like a regular index,
it is also possible to upload new packages directly to the *pr index* with ``devpi upload`` or standard tools like ``twine``.

For convenience it is also possible to list multiple packages upon first creation to let them automatically be copied:

.. code-block:: bash

    $ devpi new-pr new-feature prod/main pkg-app==1.0 app-dependency==1.2

If only the package name is given,
then the latest version is used.

Afterwards the *pull request* can be submitted for review:

.. code-block:: bash

    $ devpi submit-pr new-feature

This will ask for a message.

The state of the *pr index* is now set to ``pending``.


Reviewing a pull request
~~~~~~~~~~~~~~~~~~~~~~~~

Any user with write access to the target index (see ``acl_upload`` option of indexes in devpi-server) can now review the *pull request*.

To see current *pull requests* for an index use the ``list-prs`` command:

.. code-block:: bash

    $ devpi list-prs prod/main
    pending pull requests
        user/new-feature -> prod/main at serial 123

A review is started with the ``review-pr`` command:

.. code-block:: bash

    $ devpi review-pr new-feature

At this point the *pr index* can be used to install the new packages with ``pip`` etc just as a regular index.

Once the review is complete it can be accepted:

.. code-block:: bash

    $ devpi accept-pr new-feature

This again requires a message like for the ``submit-pr`` command.

When the *pull request* is accepted the latest contained version of all packages is copied to the target index in one atomic step.
Afterwards the *pr index* is automatically deleted.

If there have been any changes on the index after the ``review-pr`` command,
then the ``accept-pr`` command will fail.
To continue another call of ``review-pr`` with the ``-u`` option is required:

.. code-block:: bash

    $ devpi review-pr -u new-feature

This prevents unexpected changes to be accepted.
After reviewing the changes the *pull request* can be accepted again.

In case the *pull request* needs further work,
it can be rejected with the ``reject-pr`` command and a message:

.. code-block:: bash

    $ devpi reject-pr new-feature -m "See comments in ticket #42 about a bug I found."


Manual creation of pr index
~~~~~~~~~~~~~~~~~~~~~~~~~~~

It's also possible to create a *pull request* manually.
This works without ``devpi-pr`` installed alongside ``devpi-client``,
but is more complex.

First a new *pr index* needs to be created.
The index must be of type ``pr``, the target index specified in ``bases`` and ``states`` and ``messages`` be set:

.. code-block:: bash

    $ devpi index -c new-feature type=pr bases=prod/main states=new messages="New pull request"

Once the index is created, packages can be uploaded to it with ``devpi upload`` or pushed from another index with ``devpi push``.

At last the state of the index needs to be updated to ``pending`` and a state change message be added:

.. code-block:: bash

    $ devpi index new-feature states+=pending messages+="Please approve these updated packages"
