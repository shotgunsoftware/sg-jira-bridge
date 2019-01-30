# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#


class UnsuitableSyncValue(ValueError):
    """
    Base class for exceptions raised when a value can't be translated to a valid
    value for a given field.
    """
    def __init__(self, field, value, *args, **kwargs):
        """
        :param str field: The Jira field for which the exception was raised.
        :param value: The Shotgun value for which the exception was raised.
        """
        super(UnsuitableShotgunValue, self).__init__(*args, **kwargs)
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


class UnsuitableShotgunValue(UnsuitableSyncValue):
    """
    An exception raised when a Shotgun value can't be translated to a valid
    Jira value for a given field.
    """
    pass


class UnsuitableJiraValue(UnsuitableSyncValue):
    """
    An exception raised when a Jira value can't be translated to a valid
    Shotgun value for a given field.
    """
    pass
