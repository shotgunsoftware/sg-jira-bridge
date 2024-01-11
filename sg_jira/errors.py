# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#


class InvalidSyncValue(ValueError):
    """
    Base class for exceptions raised when a value can't be translated to a valid
    value for a given field.
    """

    def __init__(self, field, value, *args, **kwargs):
        """
        :param str field: The Jira or SG field for which the exception was raised.
        :param value: The Jira or SG value for which the exception was raised.
        """
        super(InvalidSyncValue, self).__init__(*args, **kwargs)
        self._field = field
        self._value = value

    @property
    def field(self):
        """
        Return the field for which the exception was raised.
        """
        return self._field

    @property
    def value(self):
        """
        Return the value for which the exception was raised.
        """
        return self._value


class InvalidShotgunValue(InvalidSyncValue):
    """
    An exception raised when a Flow Production Tracking value can't be translated to a valid
    Jira value for a given field.
    """

    pass


class InvalidJiraValue(InvalidSyncValue):
    """
    An exception raised when a Jira value can't be translated to a valid
    Flow Production Tracking value for a given field.
    """

    pass
