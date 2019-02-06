# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging
import shotgun_api3

from .utils import utf8_decode, utf8_encode

logger = logging.getLogger(__name__)


class ShotgunSession(object):
    """
    Wrap a :class:`shotgun_api3.Shotgun` instance and provide some helpers and
    session caches.

    Ensure all the values we get from Shotgun are unicode and not utf-8 encoded
    strings. Utf-8 encode unicode values before sending them to Shotgun.
    """

    # The list of Shotgun methods we need to wrap.
    _WRAP_SHOTGUN_METHODS = [
        "authenticate_human_user",
        "create",
        "find_one",
        "find",
        "update",
        "batch",
        "upload",
        "upload_thumbnail",
        "upload_filmstrip_thumbnail",
        "download_attachment",
        "get_attachment_download_url",
        "schema_entity_read",
        "schema_field_create",
        "schema_field_delete",
        "schema_field_read",
        "schema_field_update",
        "schema_read",
        "share_thumbnail",
    ]

    def __init__(self, *args, **kwargs):
        """
        Instantiate a :class:`shotgun_api3.Shotgun` with the sanitized parameters.
        """
        # Note: we use composition rather than inheritance to wrap the Shotgun
        # instance. Otherwise we would have to redefine all the methods we need
        # to wrap with some very similar code which would encode all params,
        # blindly call the original method, decode and return the result.

        safe_args = utf8_encode(args)
        safe_kwargs = utf8_encode(kwargs)
        self._shotgun = shotgun_api3.Shotgun(
            *safe_args,
            **safe_kwargs
        )

    def _get_wrapped_shotgun_method(self, method_name):
        """
        Return a wrapped Shotgun method which encode all parameters and decode
        the result before returning it.

        :param str method_name: A :class:`shotgun_api3.Shotgun` method name.
        """
        method_to_wrap = getattr(self._shotgun, method_name)

        def wrapped(*args, **kwargs):
            safe_args = utf8_encode(args)
            safe_kwargs = utf8_encode(kwargs)
            result = method_to_wrap(*safe_args, **safe_kwargs)
            return utf8_decode(result)

        return wrapped

    def __getattr__(self, attribute_name):
        """
        Called when an attribute can't be found on this class instance.

        Check if the name is one of the Shotgun method names we need to wrap,
        return a wrapped method if it is the case.
        Return the :class:`shotgun_api3.Shotgun` attribute otherwise.

        :param str attribute_name: The attribute name to retrieve.
        """
        if attribute_name in self._WRAP_SHOTGUN_METHODS:
            return self._get_wrapped_shotgun_method(attribute_name)
        return getattr(self._shotgun, attribute_name)


