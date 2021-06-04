# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import win32serviceutil
import servicemanager
import win32event
import win32service

import os
import time


class WindowsService(win32serviceutil.ServiceFramework):
    """
    Windows service wrapper

    Install this service from an elevated command prompt with::

        python win_service.py install

    Then you can use the Service Manager or run this manually with::

        python win_service.py start|stop|restart

    .. note::
        If pywin32 was installed with pip, take note of this info from the
        "Installing via PIP" section of the
        `pywin32 README on GitHub <https://github.com/mhammond/pywin32#installing-via-pip>`_

            Note that if you want to use pywin32 for "system wide" features, such as
            registering COM objects or implementing Windows Services, then you must
            run the following command from an elevated command prompt::

                python Scripts/pywin32_postinstall.py -install
    """

    _svc_name_ = "ShotgunJiraBridge"
    _svc_display_name_ = "Shotgun Jira Bridge"
    _svc_description_ = "Run the Shotgun Jira web app as a Windows service."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        """
        Stop the Windows service.

        Kills the running task nicely and then forcefully if being nice
        didn't work.
        """
        # Explored a number of options here. The simplest would have been to
        # run the webapp with in another process and then shut it down.
        # However this isn't compatible with virtualenv:
        # https://stackoverflow.com/questions/10124768/python-pywin32-windows-service-and-multiprocessing
        # http://bugs.python.org/issue5162
        # TODO: Test this without virtualenv. Shouldn't use services with virtualenv.

        # os.kill is supported on Windows in Python 2.7 but requires we know the
        # pid which we don't have easy access to.
        # See Windows-specific info: https://docs.python.org/2/library/os.html#os.kill

        # Threading option:
        # https://stackoverflow.com/a/35576127/3642440

        # taskkill allows us to use the service name so it seems the most
        # straightforward.
        # https://docs.microsoft.com/en-us/previous-versions/windows/it-pro/windows-xp/bb491009(v=technet.10)

        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        servicemanager.LogInfoMsg("Stopping ShotgunJiraBridge...")

        try:
            os.system("taskkill /fi 'SERVICES eq %s'" % self._svc_name_)
            # Give the process some time to exit nicely
            time.sleep(0.1)
            # forcefully kill the process if it's still running but ignore errors
            try:
                os.system("taskkill /f /fi 'SERVICES eq %s'" % self._svc_name_)
            except OSError:
                pass
        except OSError as e:
            # Catch the error in case the process exited between our check and our
            # attempt to stop it.
            servicemanager.LogErrorMsg(
                "Unable to shutdown %s: %s" % (self._svc_name_, e)
            )
        else:
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)
            servicemanager.LogInfoMsg("%s stopped." % self._svc_name_)

    def SvcDoRun(self):
        """
        Start the Windows service.
        """
        servicemanager.LogInfoMsg("Starting %s..." % self._svc_name_)
        self.main()
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        servicemanager.LogInfoMsg("%s started." % self._svc_name_)

    def main(self):
        """
        Primary Windows entry point

        Loads settings file location and port number from env vars if they
        are set. Otherwise falls back on defaults.

        - ``SGJIRA_SETTINGS_FILE``: defaults to settings.py located in the root
          of the sg-jira-bridge application directory
        - ``SGJIRA_PORT_NUMBER``: defaults to port 9090
        """
        # load the location of the settings file. If no env var is set, fall
        # back on a settings file located in the root of this location.
        port_number = os.environ.get("SGJIRA_PORT_NUMBER", 9090)
        settings_path = os.environ.get("SGJIRA_SETTINGS_FILE")
        if not settings_path:
            settings_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "settings.py"
            )
        servicemanager.LogInfoMsg(
            "Starting up on port number %s using settings at %s"
            % (port_number, settings_path)
        )
        try:
            import webapp

            webapp.run_server(
                port=port_number, settings=settings_path,
            )
        except Exception as e:
            servicemanager.LogErrorMsg("Unable to start %s: %s" % (self._svc_name_, e))


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(WindowsService)
