# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging

import shotgun_api3

from .constants import SG_ENTITY_SPECIAL_NAME_FIELDS, SHOTGUN_JIRA_ID_FIELD
from .utils import unicode_to_utf8, utf8_to_unicode

logger = logging.getLogger(__name__)


class ShotgunSession(object):
    """
    Wraps a :class:`shotgun_api3.shotgun.Shotgun` instance and provide some helpers and
    session caches.

    Ensures all the values we get from Flow Production Tracking are unicode and not utf-8 encoded
    strings. Utf-8 encodes unicode values before sending them to Flow Production Tracking.
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

    def __init__(self, base_url, script_name=None, *args, **kwargs):
        """
        Instantiate a :class:`shotgun_api3.shotgun.Shotgun` with the sanitized parameters.
        """
        # Note: we use composition rather than inheritance to wrap the Shotgun
        # instance. Otherwise we would have to redefine all the methods we need
        # to wrap with some very similar code which would encode all params,
        # blindly call the original method, decode and return the result.

        safe_args = unicode_to_utf8(args)
        safe_kwargs = unicode_to_utf8(kwargs)
        self._shotgun = shotgun_api3.Shotgun(
            unicode_to_utf8(base_url),
            unicode_to_utf8(script_name),
            *safe_args,
            **safe_kwargs,
        )

        self._shotgun_entity_types = []  # will be used to store FPT entities list
        self._shotgun_schemas = {}  # will be used to store FPT fields by entity type

        # Retrieve our current login, this does not seem to be available from
        # the connection?
        self._shotgun_user = self.find_one(
            "ApiUser", [["firstname", "is", script_name]], ["firstname"]
        )
        logger.info("Connected to %s." % base_url)

    @property
    def current_user(self):
        """
        Return the Flow Production Tracking user used for the connection.

        :returns: A Flow Production Tracking record dictionary with an `id` key and a `type` key.
        """
        return self._shotgun_user

    def setup(self):
        """
        Check the Flow Production Tracking site and cache site level values.

        :raises RuntimeError: if the Flow Production Tracking site was not correctly configured to
                 be used with this bridge.
        """
        self.assert_field("Project", SHOTGUN_JIRA_ID_FIELD, "text", check_unique=True)

    def assert_entity_type(self, entity_type):
        """
        Check if the given entity exists in Flow Production Tracking site.

        :param str entity_type: A Flow Production Tracking Entity type.
        :raises RuntimeError: if the entity does not exist.
        """
        if not self._shotgun_entity_types:
            self._shotgun_entity_types = self._shotgun.schema_entity_read().keys()
        if entity_type not in self._shotgun_entity_types:
            raise RuntimeError(f"Missing {entity_type} entity type in the FPT schema.")

    def assert_field(self, entity_type, field_name, field_type, check_unique=False):
        """
        Check if the given field with the given type exists for the given Flow Production Tracking
        Entity type.

        :param str entity_type: A Flow Production Tracking Entity type.
        :param str field_name: A Flow Production Tracking field name, e.g. 'sg_my_precious'.
        :param str field_type: A Flow Production Tracking field type, e.g. 'text'.
        :param bool check_unique: When ``True``, check the specified field
            is configured to only accept unique values. Default is ``False``.
        :raises RuntimeError: if the field does not exist or does not have the
                 expected type.
        """
        field = self.get_field_schema(entity_type, field_name)
        if not field:
            raise RuntimeError(
                "Missing required custom Shotgun %s field %s"
                % (
                    entity_type,
                    field_name,
                )
            )
        if field_type and field["data_type"]["value"] != field_type:
            raise RuntimeError(
                "Invalid type '%s' for Shotgun field %s.%s, it must be '%s'"
                % (field["data_type"]["value"], entity_type, field_name, field_type)
            )
        if check_unique is True:
            if field["unique"]["value"] is not True:
                raise RuntimeError(
                    "Invalid 'unique' property '%s' for Shotgun field %s.%s, "
                    "it must be 'True'"
                    % (field["unique"]["value"], entity_type, field_name)
                )

    def get_field_schema(self, entity_type, field_name):
        """
        Return the Flow Production Tracking schema for the given Entity field.

        .. note:: Flow Production Tracking schemas are cached and the bridge needs to be restarted
                  if schemas are changed in Flow Production Tracking.

        :param str entity_type: A Flow Production Tracking Entity type.
        :param str field_name: A Flow Production Tracking field name, e.g. 'sg_my_precious'.
        :returns: The Flow Production Tracking schema for the given field as a dictionary or `None`.
        """
        if entity_type not in self._shotgun_schemas:
            self._shotgun_schemas[entity_type] = self._shotgun.schema_field_read(
                entity_type
            )
        field = self._shotgun_schemas[entity_type].get(field_name)
        return field

    def clear_cached_field_schema(self, entity_type=None):
        """
        Clear all cached Flow Production Tracking schema or just the cached schema for the given
        Flow Production Tracking Entity type.

        :param str entity_type: A Flow Production Tracking Entity type or None.
        """
        if entity_type:
            logger.debug("Clearing cached Shotgun schema for %s" % entity_type)
            if entity_type in self._shotgun_schemas:
                del self._shotgun_schemas[entity_type]
        else:
            logger.debug("Clearing all cached Shotgun schemas")
            self._shotgun_schemas = {}
            self._shotgun_entity_types = []

    @staticmethod
    def get_entity_name_field(entity_type):
        """
        Return the Flow Production Tracking name field to use for the specified entity type.

        :param str entity_type: The entity type to get the name field for.
        :returns: The name field for the specified entity type.
        """
        # Deal with some known special cases and assume "code" for anything else.
        return SG_ENTITY_SPECIAL_NAME_FIELDS.get(entity_type, "code")

    def is_project_entity(self, entity_type):
        """
        Return `True` if the given Flow Production Tracking Entity type is a project Entity,
        that is an Entity linked to a Project, `False` if it is a non-project
        Entity.

        :param str entity_type: A Flow Production Tracking Entity type.
        """
        if entity_type not in self._shotgun_schemas:
            self._shotgun_schemas[entity_type] = self._shotgun.schema_field_read(
                entity_type
            )
        # We only check for standard Shotgun project field
        field_schema = self._shotgun_schemas[entity_type].get("project")
        if not field_schema:
            return False
        # We don't need to check the field data type: it is not possible to
        # to create a custom "project" field (it would be sg_project) and it
        # is very unlikely that anyone would even try to tweak this critical
        # standard field.
        return True

    def consolidate_entity(self, shotgun_entity, fields=None, retired_only=False):
        """
        Consolidate the given Flow Production Tracking Entity: collect additional field values,
        ensure the Entity name is available under a "name" key.

        :param shotgun_entity: A Flow Production Tracking Entity dictionary with at least its id
                               and its type.
        :param fields: An optional list of fields to add to the query.
        :param retired_only: An optional boolean indicating if the entity we're consolidating has been retired.
        :returns: The consolidated Flow Production Tracking Entity or `None` if it can't be retrieved.
        """

        # Define the fields we need to handle the Entity type.
        needed_fields = []
        entity_type = shotgun_entity["type"]
        name_field = self.get_entity_name_field(entity_type)

        if entity_type == "HumanUser":
            needed_fields = [name_field, "email"]
        elif entity_type == "Task":
            needed_fields = [name_field, "task_assignees"]
        else:
            needed_fields = [name_field]

        if self.is_project_entity(shotgun_entity["type"]):
            needed_fields.append("project")

        if fields:
            needed_fields.extend(fields)

        # Do a Shotgun query if any field is missing
        missing = [needed for needed in needed_fields if needed not in shotgun_entity]
        if missing:
            consolidated = self.find_one(
                shotgun_entity["type"],
                [["id", "is", shotgun_entity["id"]]],
                missing + list(shotgun_entity.keys()),
                retired_only=retired_only,
            )
            if not consolidated:
                logger.warning(
                    "Unable to find %s (%d) in Shotgun"
                    % (
                        shotgun_entity["type"],
                        shotgun_entity["id"],
                    )
                )
                return None
            shotgun_entity = consolidated

        # Ensure a consistent way to retrieve the Entity name
        if name_field != "name":
            shotgun_entity["name"] = shotgun_entity[name_field]
        return shotgun_entity

    def match_entity_by_name(self, name, entity_types, shotgun_project):
        """
        Retrieve a Flow Production Tracking Entity with the given name from the given list of
        Entity types.

        Project Flow Production Tracking Entities are restricted to the given Flow Production Tracking Project.

        :param str name: A name to match.
        :param entity_types: A list of Flow Production Tracking Entity types to consider.
        :param shotgun_project: A Flow Production Tracking Project dictionary.
        :return: A Flow Production Tracking Entity dictionary or `None`.
        """
        for entity_type in entity_types:
            name_field = self.get_entity_name_field(entity_type)
            filters = [[name_field, "is", name]]
            fields = [name_field]
            if self.is_project_entity(entity_type):
                filters.append(["project", "is", shotgun_project])
                fields.append("project")
            sg_value = self.find_one(
                entity_type,
                filters,
                fields,
            )
            if sg_value:
                return self.consolidate_entity(sg_value)
        return None

    def get_entity_page_url(self, shotgun_entity):
        """
        Return the Flow Production Tracking page url for the given Entity.

        :param shotgun_entity: A Flow Production Tracking Entity dictionary with at least a 'type'
                               key and an 'id' key.
        """
        return "%s/detail/%s/%d" % (
            self.base_url,
            shotgun_entity["type"],
            shotgun_entity["id"],
        )

    def _get_wrapped_shotgun_method(self, method_name):
        """
        Return a wrapped Flow Production Tracking method which encodes all parameters and decodes
        the result before returning it.

        :param str method_name: A :class:`~shotgun_api3.shotgun.Shotgun` method name.
        """
        method_to_wrap = getattr(self._shotgun, method_name)

        def wrapped(*args, **kwargs):
            safe_args = unicode_to_utf8(args)
            safe_kwargs = unicode_to_utf8(kwargs)
            result = method_to_wrap(*safe_args, **safe_kwargs)
            return utf8_to_unicode(result)

        return wrapped

    def __getattr__(self, attribute_name):
        """
        Called when an attribute can't be found on this class instance.

        Check if the name is one of the Flow Production Tracking method names we need to wrap,
        return a wrapped method if it is the case.
        Return the :class:`shotgun_api3.shotgun.Shotgun` attribute otherwise.

        :param str attribute_name: The attribute name to retrieve.
        """
        if attribute_name in self._WRAP_SHOTGUN_METHODS:
            return self._get_wrapped_shotgun_method(attribute_name)
        return getattr(self._shotgun, attribute_name)
