# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#


def utf8_decode(value):
    """
    Convert any string in the given value to an utf8 decoded unicode value.

    Treat containers by recursively iterating over all the values they contain.

    :param value: A string, a list or a dictionary.
    :raises: ValueError if a converted utf8 decoded key is already present in the
             original value of a dictionary.
    """
    if isinstance(value, list):
        # Convert all values
        return [utf8_decode(x) for x in value]

    if isinstance(value, tuple):
        # Convert all values
        return tuple([utf8_decode(x) for x in value])

    if isinstance(value, dict):
        # Convert the keys and the values
        decoded = {}
        for k, v in value.iteritems():
            # We need to check if there is a potential conflict between the
            # decoded key and an existing unicode key, so we can't blindly call
            # ourself here.
            if isinstance(k, str):
                decoded_key = k.decode("utf-8")
                if decoded_key in [x for x in value.keys() if isinstance(x, unicode)]:
                    raise ValueError(
                        "Utf8 decoded key %s is already present "
                        "in dictionary being decoded" % (
                            decoded_key,
                        )
                    )
            else:
                decoded_key = k
            decoded[decoded_key] = utf8_decode(v)
        return decoded

    if isinstance(value, str):
        return value.decode("utf-8")

    # Nothing to do, return the value unchanged.
    return value


def utf8_encode(value):
    """
    Convert any unicode in the given value to an utf8 encoded string value.

    Treat containers by recursively iterating over all the values they contain.

    :param value: A string, a list or a dictionary.
    :raises: ValueError if a converted utf8 encoded key is already present in the
             original value of a dictionary.
    """
    if isinstance(value, list):
        # Convert all values
        return [utf8_encode(x) for x in value]

    if isinstance(value, tuple):
        # Convert all values
        return tuple([utf8_encode(x) for x in value])

    if isinstance(value, dict):
        # Convert the keys and the values
        encoded = {}
        for k, v in value.iteritems():
            # We need to check if there is a potential conflict between the
            # encoded key and an existing str key, so we can't blindly call
            # ourself here.
            if isinstance(k, unicode):
                encoded_key = k.encode("utf-8")
                if encoded_key in [x for x in value.keys() if isinstance(x, str)]:
                    # Note: we issue the error with the unicode value to be
                    # consistent with our convention where everything is unicode
                    # and don't get potential problems with an utf-8 encoded string
                    # being used with unicode values, which would potentislly lead
                    # to UnicodeDecode errors.
                    raise ValueError(
                        "Utf8 encoded key for %s is already present "
                        "in dictionary being encoded" % (
                            k,
                        )
                    )
            else:
                encoded_key = k
            encoded[encoded_key] = utf8_encode(v)
        return encoded

    if isinstance(value, unicode):
        return value.encode("utf-8")

    # Nothing to do, return the value unchanged.
    return value
