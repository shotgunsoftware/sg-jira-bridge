# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import six


def utf8_to_unicode(value):
    """
    Convert any string in the given input to unicode. Strings are expected to be
    in utf-8 encoding.

    Treat containers by recursively iterating over all the values they contain.

    :param value: A string, a list, a tuple, or a dictionary.
    :returns: The value with all strings converted to unicode.
    :raises ValueError: if a converted UTF-8 decoded key is already present in the
             original value of a dictionary.
    """

    if six.py3:
        # we only have unicode values in Python 3 so no need to loop over everything.
        return value

    if isinstance(value, list):
        # Convert all values
        return [utf8_to_unicode(x) for x in value]

    if isinstance(value, tuple):
        # Convert all values
        return tuple([utf8_to_unicode(x) for x in value])

    if isinstance(value, dict):
        # Convert the keys and the values
        decoded = {}
        for k, v in value.items():
            # We need to check if there is a potential conflict between the
            # decoded key and an existing unicode key, so we can't blindly call
            # our self here.
            if isinstance(k, str):
                decoded_key = six.ensure_text(k)
                if decoded_key in [
                    x for x in value.keys() if isinstance(x, six.text_type)
                ]:
                    raise ValueError(
                        "UTF-8 decoded key %s is already present in dictionary "
                        "being decoded" % (decoded_key,)
                    )
            else:
                decoded_key = k
            decoded[decoded_key] = utf8_to_unicode(v)
        return decoded

    if isinstance(value, str):
        return six.ensure_text(value)

    # Nothing to do, return the value unchanged.
    return value


def unicode_to_utf8(value):
    """
    Convert any unicode in the given input to an utf8 encoded string value.

    Treat containers by recursively iterating over all the values they contain.

    :param value: A string, a list, a tuple, or a dictionary.
    :returns: The value with all unicode values converted to strings.
    :raises ValueError: if a converted UTF-8 encoded key is already present in the
             original value of a dictionary.
    """
    if six.py3:
        # In python 3 strings are unicode, so just return the value.
        return value

    if isinstance(value, list):
        # Convert all values
        return [unicode_to_utf8(x) for x in value]

    if isinstance(value, tuple):
        # Convert all values.
        return tuple([unicode_to_utf8(x) for x in value])

    if isinstance(value, dict):
        # Convert the keys and the values.
        encoded = {}
        for k, v in value.items():
            # We need to check if there is a potential conflict between the
            # encoded key and an existing str key, so we can't blindly call
            # our self here.
            if isinstance(k, six.text_type):
                encoded_key = six.ensure_str(k)
                if encoded_key in [x for x in value.keys() if isinstance(x, str)]:
                    # Note: we issue the error with the unicode value to be
                    # consistent with our convention where everything is unicode
                    # and don't get potential problems with an utf-8 encoded string
                    # being used with unicode values, which would potentially lead
                    # to UnicodeDecode errors.
                    raise ValueError(
                        "UTF-8 encoded key for %s is already present "
                        "in dictionary being encoded" % (k,)
                    )
            else:
                encoded_key = k
            encoded[encoded_key] = unicode_to_utf8(v)
        return encoded

    if isinstance(value, six.text_type):
        return six.ensure_str(value)

    # Nothing to do, return the value unchanged.
    return value
