.. currentmodule:: sg_jira

Settings
########

Settings are defined in the ``settings.py`` file in the root of the repo.
Since the settings are stored in a Python file, it allows for a lot of
flexiblity to adapt to your specific environment requirements if needed.
The settings file contains three main sections:

Authentication
**************
Credentials are retrieved by default from environment variables:

- ``SGJIRA_SG_SITE``: the Shotgun site url
- ``SGJIRA_SG_SCRIPT_NAME``: a Shotgun script user name
- ``SGJIRA_SG_SCRIPT_KEY``: the Shotgun script user Application Key
- ``SGJIRA_JIRA_SITE``: the Jira server url
- ``SGJIRA_JIRA_USER``: the system name of the Jira user used to
  connect for the sync.  This is usually your email address you
  sign in to Jira with. Jira does not have a concept of a "script"
  user so this will need to be the designated user account that
  will control the sync updates. It will need appropriate
  permissions to make any changes required.
- ``SGJIRA_JIRA_USER_SECRET``: the Jira user password or API Key.

.. note::

    **Jira Cloud** requires the use of an API token and will not work with
    a user password. See https://confluence.atlassian.com/x/Vo71Nw for information
    on how to generate a token.

    **Jira Server** will still work with a user password and does not support
    API tokens.

    For more information, see: https://developer.atlassian.com/cloud/jira/platform/jira-rest-api-basic-authentication/

You may set these in your environment or by installing
`python-dotenv <https://pypi.org/project/python-dotenv>`_ and defining these
in a ``.env`` file.

::

    # Shotgun credentials
    SGJIRA_SG_SITE='https://mysite.shotgunstudio.com'
    SGJIRA_SG_SCRIPT_NAME='sg-jira-bridge'
    SGJIRA_SG_SCRIPT_KEY='01234567@abcdef0123456789'

    # Jira credentials
    SGJIRA_JIRA_SITE='https://mystudio.atlassian.net'
    SGJIRA_JIRA_USER='richard.hendricks@piedpiper.com'
    SGJIRA_JIRA_USER_SECRET='youkn0wwh@tapa$5word1smAKeitag0odone3'

Logging
*******
The SG-Jira-Bridge uses standard Python logging. The logging configuration is
stored in a ``LOGGING`` *dict* using the standard :mod:`logging.config` format.


Sync Settings
*************
The sync settings are stored in a ``SYNC`` *dict* in the format:

::

    SYNC = {
        "sync_settings_name": {
            # The Syncer class to use with the module name included
            "syncer": "sg_jira.MyCustomSyncer",
            # And the specific settings which are passed to its __init__() method
            "settings": {
                "my_setting_name": "My Setting Value"
            },
        }
    }

Each key is a settings name that contains a dictionary containing the syncer
and the settings to use. The key is the settings name used when composing the
URL for SG Jira Bridge. For example,
``http://localhost:9090/sg2jira/my_settings`` uses the settings named
``my_settings``.

- **syncer**: The syncer class to use in the format ``module_name.class_name``.
- **settings**: A dictionary containing the settings for the syncer where the
  key is the setting name and value is it's value. These settings will be used
  as parameters when instantiating the syncer class.

Each set of ``SYNC`` settings defined in your ``settings.py`` file must
define a single :class:`Syncer`.

Custom syncers can be referenced in the settings file with their module path
and their specific settings. You can easily allow the bridge to load your
syncer by adding the directory that contains your custom syncer using
``sys.path``.

For example::

    # Additional paths can be added for custom syncers
    sys.path.append(os.path.abspath("./examples"))

    SYNC = {
        "default": {
            # The syncer class to use
            "syncer": "sg_jira.TaskIssueSyncer",
            # And the specific settings which are passed to its __init__() method
            "settings": {
                "foo": "bar"
            },
        },
        "test": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "example_sync.ExampleSync",
            "settings": {
                "log_level": logging.DEBUG
            },
        }
    }

Useful Patterns
===============
Rather than having to edit your settings in order to enable/disable testing,
it may be useful to have two settings for your custom syncer, one for
production and one for testing. In your testing settings you may wish to
simply enable ``DEBUG`` level logging messages.

You can take it a step further and have a base settings definition and then
load that for other settings and only override the settings you need. This
overly simplified example might look something like this::

    import logging
    import copy

    SYNC = {
        "default": {
            # The syncer class to use
            "syncer": "sg_jira.TaskIssueSyncer",
            # And the specific settings which are passed to its __init__() method
            "settings": {
                "foo": "bar",
                "color": "orange",
                "do_something": False,
                "log_level": logging.INFO
            },
        }
    }

    # create settings for default_test from default
    SYNC["test_settings"] = copy.deepcopy(SYNC["default"])

    # override the settings we need
    SYNC["test_settings"]["settings"].update({
        "log_level": logging.DEBUG,
        "color": "red"
    })
