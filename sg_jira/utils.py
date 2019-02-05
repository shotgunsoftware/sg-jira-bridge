# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#


def utf8_decode(value):
    """
    Convert any string in the given value to an utf8 decoded unicode value.

    Recursively treat containers by iterating on all the values they contain.

    :param value: A string, a list or a dictionary.
    :raises: ValueError if an utf8 decoded key is already present in the original
             value of a dictionary.
    """
    if isinstance(value, list):
        # Convert all values
        return [utf8_decode(x) for x in value]

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
                        "Utf8 decoded key for %s is already present "
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
