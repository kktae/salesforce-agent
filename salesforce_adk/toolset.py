"""Salesforce Toolset implementing BaseToolset pattern for ADK."""

import logging
from typing import Any, Union, cast

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset, ToolPredicate
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from simple_salesforce.api import Salesforce

from salesforce_adk.auth import (
    AGENTSPACE_MODE,
    SALESFORCE_API_VERSION,
    SALESFORCE_AUTH_CONFIG,
    SALESFORCE_AUTH_ID,
    SALESFORCE_INSTANCE_URL,
    SALESFORCE_LOGIN_URL,
    AUTH_PENDING_KEY,
    AUTH_PENDING_RESPONSE,
    TOKEN_CACHE_KEY,
    INSTANCE_URL_CACHE_KEY,
)
from salesforce_adk.operations import SalesforceOperations

logger = logging.getLogger(__name__)


class SalesforceToolset(BaseToolset):
    """
    Salesforce toolset providing all Salesforce operations as ADK tools.

    Uses BaseToolset pattern for cleaner tool management.
    Handles OAuth authentication automatically via ADK's built-in mechanisms.
    """

    tool_name_prefix: str = ""

    def __init__(self, tool_filter: ToolPredicate | None = None):
        """Initialize the Salesforce toolset.

        Args:
            tool_filter: Optional predicate to filter which tools are exposed
        """
        self._tool_filter = tool_filter

    async def get_tools(
        self,
        readonly_context: Any = None,
    ) -> list[BaseTool]:
        """Return all Salesforce tools.

        Args:
            readonly_context: Optional context (unused)

        Returns:
            List of FunctionTool instances for all Salesforce operations
        """
        tools = [
            # Query tools
            FunctionTool(func=self.salesforce_query),
            FunctionTool(func=self.salesforce_query_all),
            FunctionTool(func=self.salesforce_query_more),
            FunctionTool(func=self.salesforce_search),
            # Record CRUD tools
            FunctionTool(func=self.salesforce_get_record),
            FunctionTool(func=self.salesforce_create_record),
            FunctionTool(func=self.salesforce_update_record),
            FunctionTool(func=self.salesforce_delete_record),
            FunctionTool(func=self.salesforce_upsert_record),
            # Metadata tools
            FunctionTool(func=self.salesforce_describe_object),
            FunctionTool(func=self.salesforce_list_objects),
            FunctionTool(func=self.salesforce_get_object_fields),
            # Bulk API tools
            FunctionTool(func=self.salesforce_bulk_query),
            FunctionTool(func=self.salesforce_bulk_insert),
            FunctionTool(func=self.salesforce_bulk_update),
            FunctionTool(func=self.salesforce_bulk_delete),
        ]

        if self._tool_filter:
            tools = [t for t in tools if self._tool_filter(t, readonly_context)]

        return list(tools)

    async def _get_client(
        self,
        tool_context: ToolContext,
    ) -> Union[Salesforce, dict, None]:
        """Get an authenticated Salesforce client using ADK OAuth flow.

        This method:
        1. Checks for cached access token in tool_context.state
        2. If no token, requests OAuth authentication from user
        3. Caches the token and instance_url for future use
        4. Returns a simple_salesforce.Salesforce client

        Args:
            tool_context: The ADK ToolContext for managing auth state

        Returns:
            Authenticated Salesforce client, or None if auth is pending,
            or dict with "error" key if token exchange failed
        """
        # --- Agentspace mode: platform-injected token ---
        if AGENTSPACE_MODE:
            assert SALESFORCE_AUTH_ID is not None
            access_token = tool_context.state.get(SALESFORCE_AUTH_ID)
            if not access_token:
                return {
                    "error": f"No access token injected by Agentspace. Verify Authorization resource for auth_id='{SALESFORCE_AUTH_ID}'."
                }

            instance_url = SALESFORCE_INSTANCE_URL
            if not instance_url:
                return {
                    "error": "SALESFORCE_INSTANCE_URL is required in Agentspace mode."
                }

            return Salesforce(instance_url=instance_url, session_id=access_token, version=SALESFORCE_API_VERSION)

        # --- Local/dev mode: standard ADK OAuth flow ---

        # Check for cached token
        access_token = tool_context.state.get(TOKEN_CACHE_KEY)
        instance_url = tool_context.state.get(
            INSTANCE_URL_CACHE_KEY, SALESFORCE_INSTANCE_URL
        )

        if access_token and instance_url:
            return Salesforce(
                instance_url=instance_url,
                session_id=access_token,
                version=SALESFORCE_API_VERSION,
            )

        # No cached token, check if we have a pending auth response
        auth_response = tool_context.get_auth_response(SALESFORCE_AUTH_CONFIG)

        if auth_response and auth_response.oauth2:
            oauth2_response = auth_response.oauth2
            access_token = oauth2_response.access_token
            refresh_token = oauth2_response.refresh_token

            logger.debug("Obtained OAuth2 response from ADK auth flow.")
            logger.debug("Access token present: %s", bool(access_token))
            logger.debug("Refresh token present: %s", bool(refresh_token))

            if not access_token:
                tool_context.state[AUTH_PENDING_KEY] = False
                return {
                    "error": "OAuth token exchange failed. Please check your Salesforce Connected App credentials."
                }

            # Get instance_url from OAuth response or use configured default
            response_instance_url = getattr(oauth2_response, "instance_url", None)
            if response_instance_url:
                logger.debug(
                    "Using instance_url from OAuth response: %s",
                    response_instance_url,
                )
                instance_url = response_instance_url
            elif not instance_url:
                instance_url = SALESFORCE_INSTANCE_URL or SALESFORCE_LOGIN_URL
            logger.debug("Using instance_url: %s", instance_url)

            # Cache the tokens
            tool_context.state[TOKEN_CACHE_KEY] = access_token
            tool_context.state[INSTANCE_URL_CACHE_KEY] = instance_url
            tool_context.state[AUTH_PENDING_KEY] = False

            return Salesforce(
                instance_url=instance_url,
                session_id=access_token,
                version=SALESFORCE_API_VERSION,
            )

        # Check if auth is already pending
        if tool_context.state.get(AUTH_PENDING_KEY):
            return None

        # Request authentication
        tool_context.state[AUTH_PENDING_KEY] = True
        tool_context.request_credential(SALESFORCE_AUTH_CONFIG)
        return None

    def _check_auth(self, client: Union[Salesforce, dict, None]) -> dict | None:
        """Check if client is valid, return error response if not.

        Args:
            client: Result from _get_client

        Returns:
            Error/pending dict if client is invalid, None if valid
        """
        if client is None:
            return AUTH_PENDING_RESPONSE
        if isinstance(client, dict):
            return client
        return None

    # ==================== Query Tools ====================

    async def salesforce_query(
        self,
        soql: str,
        include_deleted: bool = False,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Execute a SOQL query against Salesforce.

        Args:
            soql: SOQL query string (e.g., "SELECT Id, Name FROM Account LIMIT 10")
            include_deleted: If True, includes deleted and archived records
            tool_context: ADK tool context for authentication

        Returns:
            Query results containing totalSize, done, records, and nextRecordsUrl
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.query(soql, include_deleted=include_deleted)

    async def salesforce_query_all(
        self,
        soql: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Execute a SOQL query including deleted and archived records.

        Args:
            soql: SOQL query string
            tool_context: ADK tool context for authentication

        Returns:
            Query results including deleted/archived records
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.query_all(soql)

    async def salesforce_query_more(
        self,
        next_records_url: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Fetch additional records from a paginated query result.

        Args:
            next_records_url: The nextRecordsUrl from a previous query result
            tool_context: ADK tool context for authentication

        Returns:
            Additional query results with records and possibly another nextRecordsUrl
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.query_more(next_records_url)

    async def salesforce_search(
        self,
        sosl: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Execute a SOSL (Salesforce Object Search Language) search.

        Args:
            sosl: SOSL search string (e.g., "FIND {Acme} IN ALL FIELDS RETURNING Account(Name)")
            tool_context: ADK tool context for authentication

        Returns:
            Search results grouped by object type
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.search(sosl)

    # ==================== Record CRUD Tools ====================

    async def salesforce_get_record(
        self,
        sobject: str,
        record_id: str,
        fields: str = "",
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Get a Salesforce record by its ID.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact", "Lead")
            record_id: The Salesforce record ID (18-character ID)
            fields: Comma-separated list of fields to retrieve. If empty, returns all fields.
            tool_context: ADK tool context for authentication

        Returns:
            Record data with requested fields and attributes
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        fields_list = (
            [f.strip() for f in fields.split(",") if f.strip()] if fields else None
        )
        return ops.get_record(sobject, record_id, fields_list)

    async def salesforce_create_record(
        self,
        sobject: str,
        data: dict[str, Any],
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Create a new Salesforce record.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact")
            data: Dictionary of field names and values for the new record
            tool_context: ADK tool context for authentication

        Returns:
            Result containing id, success, and errors
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.create_record(sobject, data)

    async def salesforce_update_record(
        self,
        sobject: str,
        record_id: str,
        data: dict[str, Any],
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Update an existing Salesforce record.

        Args:
            sobject: SObject type name
            record_id: The Salesforce record ID to update
            data: Dictionary of field names and new values
            tool_context: ADK tool context for authentication

        Returns:
            Result with success status and status_code
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        status_code = ops.update_record(sobject, record_id, data)
        return {
            "success": status_code == 204,
            "status_code": status_code,
            "record_id": record_id,
        }

    async def salesforce_delete_record(
        self,
        sobject: str,
        record_id: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Delete a Salesforce record.

        Args:
            sobject: SObject type name
            record_id: The Salesforce record ID to delete
            tool_context: ADK tool context for authentication

        Returns:
            Result with success status and status_code
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        status_code = ops.delete_record(sobject, record_id)
        return {
            "success": status_code == 204,
            "status_code": status_code,
            "record_id": record_id,
        }

    async def salesforce_upsert_record(
        self,
        sobject: str,
        external_id_field: str,
        data: dict[str, Any],
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Upsert a record using an external ID field.

        Args:
            sobject: SObject type name
            external_id_field: Name of the external ID field to match on
            data: Record data including the external ID field value
            tool_context: ADK tool context for authentication

        Returns:
            Result containing id, success, and created flag
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.upsert_record(sobject, external_id_field, data)

    # ==================== Metadata Tools ====================

    async def salesforce_describe_object(
        self,
        sobject: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """
        Get complete metadata for a Salesforce SObject.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact", "CustomObject__c")
            tool_context: ADK tool context for authentication

        Returns:
            Complete object metadata including name, label, fields, recordTypeInfos, etc.
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.describe_object(sobject)

    async def salesforce_list_objects(
        self,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """
        List all available SObjects in the Salesforce org.

        Args:
            tool_context: ADK tool context for authentication

        Returns:
            Dictionary containing sobjects list with name, label, keyPrefix, etc.
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.list_objects()

    async def salesforce_get_object_fields(
        self,
        sobject: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Get field information for a Salesforce SObject.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact")
            tool_context: ADK tool context for authentication

        Returns:
            List of field metadata dictionaries with name, label, type, etc.
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_object_fields(sobject)

    # ==================== Bulk API Tools ====================

    async def salesforce_bulk_query(
        self,
        sobject: str,
        soql: str,
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Execute a bulk query for large datasets.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact")
            soql: SOQL query string
            tool_context: ADK tool context for authentication

        Returns:
            List of all matching records
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.bulk_query(sobject, soql)

    async def salesforce_bulk_insert(
        self,
        sobject: str,
        records: list[dict[str, Any]],
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Bulk insert multiple records at once.

        Args:
            sobject: SObject type name
            records: List of record data dictionaries
            tool_context: ADK tool context for authentication

        Returns:
            List of results for each record with success, id, and errors
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.bulk_insert(sobject, records)

    async def salesforce_bulk_update(
        self,
        sobject: str,
        records: list[dict[str, Any]],
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Bulk update multiple records at once.

        Args:
            sobject: SObject type name
            records: List of record data with Id field
            tool_context: ADK tool context for authentication

        Returns:
            List of results for each record with success, id, and errors
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.bulk_update(sobject, records)

    async def salesforce_bulk_delete(
        self,
        sobject: str,
        record_ids: list[str],
        *,
        tool_context: ToolContext,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Bulk delete multiple records at once.

        Args:
            sobject: SObject type name
            record_ids: List of record IDs to delete
            tool_context: ADK tool context for authentication

        Returns:
            List of results for each record with success, id, and errors
        """
        client = await self._get_client(tool_context)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.bulk_delete(sobject, record_ids)
