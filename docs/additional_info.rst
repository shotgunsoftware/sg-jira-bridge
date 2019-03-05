.. _additional_info:

Additional Information
######################

.. _using-pipenv:

Using Pipenv
============
if you're using `pipenv <https://pipenv.readthedocs.io>`_ and would like to use
it for installing SG Jira Bridge or shotgunEvents, follow these instructions:

SG Jira Bridge
--------------
This code ships with a `Pipfile` and `Pipfile.lock` which makes setting up a
virtualenv and installing the required packages and dependencies simple.

.. code-block:: bash

    # creates virtual env and nstalls the required packages
    # use the --dev switch if you also want to install the dev packages
    $ pipenv install

shotgunEvents
-------------
There is no Pipfile in this repo but you can create one using the following:

.. code-block:: bash

    # create a virtualenv (the shell will be activated automatically)
    # if python is not in your PATH, you can use pipenv --python /path/to/python/2.7
    $ pipenv --python 2.7

    # Install the required packages
    $ pipenv install requests 
    $ pipenv install -e git+https://github.com/shotgunsoftware/python-api.git@v3.0.39#egg=shotgun-api3

