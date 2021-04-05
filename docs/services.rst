Installing as a Service
#######################

SG Jira Bridge can be run as a service on MacOS/Linux and Windows.

MacOS and Linux
***************
On MacOS and Linux, the ``service.py`` script can be used with systemd. It
accepts parameters from the command-line and responds to the standard commands::

    usage: service.py [-h] [--pid_file PID_FILE] [--log_file LOG_FILE]
                  [--port PORT] --settings SETTINGS
                  {start,stop,restart,status}

Parameters
==========
- **-h**: Display the usage help.
- **--pid_file**: Full path to the pid file used by the service. Defaults to
  ``/tmp/sg_jira.pid``.
- **--log_file**: An optional log file to use for the daemon output. By
  default the daemon uses a syslog handler.
- **--port**: The port number for the web app to listen on. Defaults to ``9090``.
- **--settings**: (required) Full path to settings file for the web app.

Windows
*******
The ``win_service.py`` script can be installed to allow the Service Manager
to control SG Jira Bridge.

Environment Variables
=====================
Environment variables are used to specify the settings and port parameters.

- ``SGJIRA_SETTINGS_FILE``: Full path to settings file for the web app. If not
  provided, the app will look for a ``settings.py`` file in the root of the
  SG Jira Bridge directory (where it exists in the default structure).
- ``SGJIRA_PORT_NUMBER``: The port number for the web app to listen on.
  Defaults to ``9090``.

Installing the Service
======================
The Windows service requires the
`Python for Win32 (pywin32) extensions <https://pypi.org/project/pywin32/>`_.

.. note::
    If installing pywin32 with ``pip install pywin32``, the following must be
    run after the installation in order to allow it to manage services::

        python Scripts/pywin32_postinstall.py -install

    See https://github.com/mhammond/pywin32#installing-via-pip for more info.

Install the service from an elevanted command prompt with::

    python win_service.py install

Then you can control SG Jira Bridge via the Service Manager app or using::

    python win_service.py start|stop|restart

Logging
=======
Log messages from the Windows Service are logged to the Event Viewer.
