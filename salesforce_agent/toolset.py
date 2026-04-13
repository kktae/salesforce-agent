"""Salesforce Toolset implementing BaseToolset pattern for ADK."""

import logging
from datetime import datetime
from typing import Any, Union, cast

from google.adk.auth.auth_credential import AuthCredential
from google.adk.tools.authenticated_function_tool import AuthenticatedFunctionTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset, ToolPredicate
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from simple_salesforce.api import Salesforce

from salesforce_agent.auth import (
    AGENTSPACE_MODE,
    SALESFORCE_API_VERSION,
    SALESFORCE_AUTH_CONFIG,
    SALESFORCE_AUTH_ID,
    SALESFORCE_INSTANCE_URL,
    SALESFORCE_LOGIN_URL,
    INSTANCE_URL_CACHE_KEY,
)
from salesforce_agent.operations import SalesforceOperations

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
        super().__init__(tool_filter=tool_filter)
        self._tool_filter = tool_filter

    async def get_tools(
        self,
        readonly_context: Any = None,
    ) -> list[BaseTool]:
        """Return all Salesforce tools.

        Args:
            readonly_context: Optional context (unused)

        Returns:
            List of tool instances for all Salesforce operations
        """

        def make_tool(func) -> BaseTool:
            if AGENTSPACE_MODE:
                tool = FunctionTool(func=func)
                tool._ignore_params.append("credential")
                return tool
            return AuthenticatedFunctionTool(
                func=func,
                auth_config=SALESFORCE_AUTH_CONFIG,
            )

        tools = [
            # Query tools
            make_tool(self.salesforce_query),
            make_tool(self.salesforce_query_all),
            make_tool(self.salesforce_query_more),
            make_tool(self.salesforce_search),
            # Record CRUD tools
            make_tool(self.salesforce_get_record),
            make_tool(self.salesforce_create_record),
            make_tool(self.salesforce_update_record),
            make_tool(self.salesforce_delete_record),
            make_tool(self.salesforce_upsert_record),
            # Metadata tools
            make_tool(self.salesforce_describe_object),
            make_tool(self.salesforce_list_objects),
            make_tool(self.salesforce_get_object_fields),
            # Currency tools
            make_tool(self.salesforce_get_currency_config),
            # DateTime tools (no auth required)
            FunctionTool(func=self.get_current_datetime),
            # Identity tools
            make_tool(self.salesforce_get_user_identity),
            # Report tools
            make_tool(self.salesforce_list_reports),
            make_tool(self.salesforce_run_report),
            make_tool(self.salesforce_describe_report),
            make_tool(self.salesforce_run_report_async),
            make_tool(self.salesforce_get_report_instance),
            # Dashboard tools
            make_tool(self.salesforce_list_dashboards),
            make_tool(self.salesforce_get_dashboard_results),
            make_tool(self.salesforce_describe_dashboard),
            make_tool(self.salesforce_get_dashboard_status),
            make_tool(self.salesforce_refresh_dashboard),
            # File & Content tools
            make_tool(self.salesforce_download_file),
            make_tool(self.salesforce_get_record_files),
            # Approval tools
            make_tool(self.salesforce_get_approval_history),
            make_tool(self.salesforce_submit_approval),
            make_tool(self.salesforce_approve_reject),
            make_tool(self.salesforce_get_pending_approvals),
            # Bulk API tools
            make_tool(self.salesforce_bulk_query),
            make_tool(self.salesforce_bulk_insert),
            make_tool(self.salesforce_bulk_update),
            make_tool(self.salesforce_bulk_delete),
        ]

        if self._tool_filter:
            tools = [t for t in tools if self._tool_filter(t, readonly_context)]

        return list(tools)

    async def _get_client(
        self,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> Union[Salesforce, dict]:
        """Get an authenticated Salesforce client.

        In **Agentspace mode** the platform injects the access token into
        ``tool_context.state[SALESFORCE_AUTH_ID]`` — no user interaction needed.

        In **local/dev mode** the credential is injected by
        ``AuthenticatedFunctionTool``, which handles the entire OAuth flow
        (including cross-turn persistence via ``CredentialService`` and
        automatic token refresh) before the tool function is called.

        Only ``instance_url`` is cached separately because it is a
        Salesforce-specific field that ADK does not manage.

        Args:
            tool_context: The ADK ToolContext for managing auth state.
            credential: OAuth2 credential injected by AuthenticatedFunctionTool.

        Returns:
            Authenticated Salesforce client, or dict with ``"error"`` key on failure.
        """
        # --- Agentspace mode: platform-injected token ---
        if AGENTSPACE_MODE:
            if not SALESFORCE_AUTH_ID:
                return {
                    "error": "SALESFORCE_AUTH_ID is required in Agentspace mode. Set it in the environment."
                }
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

            return Salesforce(
                instance_url=instance_url,
                session_id=access_token,
                version=SALESFORCE_API_VERSION,
            )

        # --- Local/dev mode: credential injected by AuthenticatedFunctionTool ---
        if not credential or not credential.oauth2:
            return {
                "error": "No OAuth2 credential available. Please authenticate first."
            }

        access_token = credential.oauth2.access_token

        instance_url = (
            getattr(credential.oauth2, "instance_url", None)
            or tool_context.state.get(INSTANCE_URL_CACHE_KEY)
            or SALESFORCE_INSTANCE_URL
            or SALESFORCE_LOGIN_URL
        )
        tool_context.state[INSTANCE_URL_CACHE_KEY] = instance_url

        return Salesforce(
            instance_url=instance_url,
            session_id=access_token,
            version=SALESFORCE_API_VERSION,
        )

    def _check_auth(self, client: Union[Salesforce, dict]) -> dict | None:
        """Check if client is valid, return error response if not.

        Args:
            client: Result from _get_client

        Returns:
            Error dict if client is invalid, None if valid
        """
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Execute a SOQL query against Salesforce.

        Args:
            soql: SOQL query string (e.g., "SELECT Id, Name FROM Account LIMIT 200")
            include_deleted: If True, includes deleted and archived records

        Returns:
            Query results containing totalSize, done, records, and nextRecordsUrl
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.query(soql, include_deleted=include_deleted)

    async def salesforce_query_all(
        self,
        soql: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Execute a SOQL query including soft-deleted and archived records.

        Use this instead of salesforce_query when you need to find records
        that have been moved to the Recycle Bin or archived.

        Args:
            soql: SOQL query string

        Returns:
            Query results including deleted/archived records
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.query_all(soql)

    async def salesforce_query_more(
        self,
        next_records_url: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Fetch additional records from a paginated query result.

        Args:
            next_records_url: The nextRecordsUrl from a previous query result

        Returns:
            Additional query results with records and possibly another nextRecordsUrl
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.query_more(next_records_url)

    async def salesforce_search(
        self,
        sosl: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Execute a SOSL (Salesforce Object Search Language) search.

        Args:
            sosl: SOSL search string (e.g., "FIND {Acme} IN ALL FIELDS RETURNING Account(Name)")

        Returns:
            Search results grouped by object type
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get a Salesforce record by its ID.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact", "Lead")
            record_id: The Salesforce record ID (18-character ID)
            fields: Comma-separated list of fields to retrieve. If empty, returns all fields.

        Returns:
            Record data with requested fields and attributes
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Create a new Salesforce record.

        Use salesforce_describe_object first to check required fields
        if you are unsure about the object's schema.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact")
            data: Dictionary of field names and values for the new record

        Returns:
            Result containing id, success, and errors
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Update an existing Salesforce record.

        Args:
            sobject: SObject type name
            record_id: The Salesforce record ID to update
            data: Dictionary of field names and new values

        Returns:
            Result with success status and status_code
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        result = ops.update_record(sobject, record_id, data)
        if isinstance(result, dict):
            return result
        return {
            "success": result == 204,
            "status_code": result,
            "record_id": record_id,
        }

    async def salesforce_delete_record(
        self,
        sobject: str,
        record_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Delete a Salesforce record. This action is irreversible — confirm
        with the user before executing.

        Args:
            sobject: SObject type name
            record_id: The Salesforce record ID to delete

        Returns:
            Result with success status and status_code
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        result = ops.delete_record(sobject, record_id)
        if isinstance(result, dict):
            return result
        return {
            "success": result == 204,
            "status_code": result,
            "record_id": record_id,
        }

    async def salesforce_upsert_record(
        self,
        sobject: str,
        external_id_field: str,
        data: dict[str, Any],
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Upsert a record using an external ID field.

        Args:
            sobject: SObject type name
            external_id_field: Name of the external ID field to match on
            data: Record data including the external ID field value

        Returns:
            Result containing id, success, and created flag
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get complete metadata for a Salesforce SObject.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact", "CustomObject__c")

        Returns:
            Complete object metadata including name, label, fields, recordTypeInfos, etc.
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.describe_object(sobject)

    async def salesforce_list_objects(
        self,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any] | None:
        """List all available SObjects in the Salesforce org.

        Use this to verify an object exists before querying it,
        especially for custom objects.

        Returns:
            Dictionary containing sobjects list with name, label, keyPrefix, etc.
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.list_objects()

    async def salesforce_get_object_fields(
        self,
        sobject: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Get field information for a Salesforce SObject.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact")

        Returns:
            List of field metadata dictionaries with name, label, type, etc.
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_object_fields(sobject)

    # ==================== Currency Tools ====================

    async def salesforce_get_currency_config(
        self,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get the org's Multi-Currency configuration including corporate currency,
        active currencies with conversion rates, and ACM status.

        If Multi-Currency is not enabled, returns multi_currency_enabled=false.

        Returns:
            Currency configuration with corporate_currency, currencies,
            advanced_currency_management, and dated_rates
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_currency_config()

    # ==================== DateTime Tools ====================

    async def get_current_datetime(self) -> dict[str, Any]:
        """Get the current date and time.

        Use this when the user asks for the current time, or when you need
        a precise timestamp for calculations or record updates.

        Returns:
            Current datetime with date, time, timezone, and day_of_week
        """
        from zoneinfo import ZoneInfo

        from salesforce_agent.auth import AGENT_TIMEZONE

        tz = ZoneInfo(AGENT_TIMEZONE)
        now = datetime.now(tz)
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timezone": AGENT_TIMEZONE,
            "day_of_week": now.strftime("%A"),
            "iso": now.isoformat(),
        }

    # ==================== Identity Tools ====================

    async def salesforce_get_user_identity(
        self,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get the current authenticated user's identity information.

        Use this when the user refers to "my" records or asks "who am I".
        The returned user_id can be used as OwnerId in SOQL WHERE clauses.

        Returns:
            User identity with user_id, organization_id, name, email,
            username, zoneinfo, locale, and user_type
        """
        from salesforce_agent.auth import USER_IDENTITY_CACHE_KEY

        # 캐시 확인
        cached = tool_context.state.get(USER_IDENTITY_CACHE_KEY)
        if cached and isinstance(cached, dict):
            return cached

        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        identity = ops.get_user_identity()

        # 성공 시 캐시 저장
        if isinstance(identity, dict) and "error" not in identity:
            tool_context.state[USER_IDENTITY_CACHE_KEY] = identity
            tool_context.state["_user_context"] = (
                f"{identity.get('name')} "
                f"(username: {identity.get('preferred_username')}, "
                f"user_id: {identity.get('user_id')})"
            )

        return identity

    # ==================== Report Tools ====================

    async def salesforce_list_reports(
        self,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """List recently viewed Salesforce reports (up to 200).

        Returns:
            List of report summaries with id, name, url, etc.
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.list_reports()

    async def salesforce_run_report(
        self,
        report_id: str,
        filters: list[dict[str, Any]] | None = None,
        include_details: bool = True,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Execute a Salesforce report synchronously.

        Runs the report and returns results immediately. Supports dynamic
        filters to narrow results without modifying the saved report definition.
        Note: API returns a maximum of 2,000 detail rows.

        Args:
            report_id: The 15 or 18-character Salesforce report ID
            filters: Optional list of dynamic filters. Each filter is a dict with
                     "column" (API name), "operator" (e.g. "equals", "greaterThan"),
                     and "value" (filter value).
            include_details: If True (default), include individual detail rows

        Returns:
            Report result with reportMetadata, factMap, groupingsDown, groupingsAcross
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.run_report(
            report_id, filters=filters, include_details=include_details
        )

    async def salesforce_describe_report(
        self,
        report_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get metadata for a Salesforce report.

        Returns the report's structure including columns, filters, groupings,
        and report type information. Useful for understanding a report before
        running it or applying dynamic filters.

        Args:
            report_id: The 15 or 18-character Salesforce report ID

        Returns:
            Report metadata with reportMetadata, reportTypeMetadata, reportExtendedMetadata
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.describe_report(report_id)

    async def salesforce_run_report_async(
        self,
        report_id: str,
        filters: list[dict[str, Any]] | None = None,
        include_details: bool = True,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Request an asynchronous execution of a Salesforce report.

        Use this for large reports that may exceed the synchronous timeout (2 min).
        Returns an instance ID that can be used with salesforce_get_report_instance
        to poll for results. Async results are retained for 24 hours.

        Args:
            report_id: The 15 or 18-character Salesforce report ID
            filters: Optional list of dynamic filters (same format as salesforce_run_report)
            include_details: If True (default), include individual detail rows

        Returns:
            Instance info containing "id" (instance ID), "status", and "requestDate"
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.run_report_async(
            report_id, filters=filters, include_details=include_details
        )

    async def salesforce_get_report_instance(
        self,
        report_id: str,
        instance_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get the result of an asynchronous report execution.

        Retrieves results for a previously submitted async report run.
        If the report is still running, the status field will indicate progress.

        Args:
            report_id: The 15 or 18-character Salesforce report ID
            instance_id: The instance ID returned by salesforce_run_report_async

        Returns:
            Report result (same structure as salesforce_run_report) or status if still running
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_report_instance(report_id, instance_id)

    # ==================== Dashboard Tools ====================

    async def salesforce_list_dashboards(
        self,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """List recently viewed Salesforce dashboards.

        Returns:
            List of dashboard summaries with id, name, url, etc.
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.list_dashboards()

    async def salesforce_get_dashboard_results(
        self,
        dashboard_id: str,
        filter1: str | None = None,
        filter2: str | None = None,
        filter3: str | None = None,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get dashboard data and component results with optional filters.

        Dashboards support up to 3 positional filters (filter1/2/3).
        Use salesforce_describe_dashboard first to see which filters are
        configured and what values they accept.

        Args:
            dashboard_id: The 15 or 18-character Salesforce dashboard ID
            filter1: Optional first positional filter value
            filter2: Optional second positional filter value
            filter3: Optional third positional filter value

        Returns:
            Dashboard data with componentData containing each component's results
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_dashboard_results(
            dashboard_id, filter1=filter1, filter2=filter2, filter3=filter3
        )

    async def salesforce_describe_dashboard(
        self,
        dashboard_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get metadata for a Salesforce dashboard.

        Returns the dashboard's structure including components, filters,
        and layout information. Use this to discover available filters
        before calling salesforce_get_dashboard_results.

        Args:
            dashboard_id: The 15 or 18-character Salesforce dashboard ID

        Returns:
            Dashboard metadata with components, filters, and layout
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.describe_dashboard(dashboard_id)

    async def salesforce_get_dashboard_status(
        self,
        dashboard_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Check dashboard data freshness and refresh status per component.

        Use this to determine if dashboard data is stale before deciding
        whether to trigger a refresh with salesforce_refresh_dashboard.

        Args:
            dashboard_id: The 15 or 18-character Salesforce dashboard ID

        Returns:
            Status info with component-level data freshness and refresh state
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_dashboard_status(dashboard_id)

    async def salesforce_refresh_dashboard(
        self,
        dashboard_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Trigger a dashboard data refresh.

        Refreshes all component data in the dashboard. Limited to 200
        refreshes per hour per org. Use salesforce_get_dashboard_status
        to check when the refresh completes (status becomes IDLE).

        Args:
            dashboard_id: The 15 or 18-character Salesforce dashboard ID

        Returns:
            Refresh result with updated dashboard data
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.refresh_dashboard(dashboard_id)

    # ==================== File & Content Tools ====================

    async def salesforce_download_file(
        self,
        record_id: str,
        sobject: str = "ContentVersion",
        blob_field: str = "VersionData",
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Download file content from a Salesforce ContentVersion or Attachment record.

        Returns the file as base64-encoded content along with metadata (title,
        extension, size). Use salesforce_get_record_files first to discover
        file IDs attached to a record.

        Args:
            record_id: The ContentVersion ID or Attachment ID to download
            sobject: SObject type - "ContentVersion" (default) or "Attachment"
            blob_field: Blob field name - "VersionData" (default for ContentVersion)
                        or "Body" (for Attachment)

        Returns:
            Dict with content_base64 (base64-encoded file content), size_bytes,
            and metadata (title, file_extension, content_size, etc.)
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.download_file(record_id, sobject=sobject, blob_field=blob_field)

    async def salesforce_get_record_files(
        self,
        record_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """List all files attached to a Salesforce record via ContentDocumentLink.

        Queries ContentDocumentLink to find all files (ContentDocument) linked
        to the given record. Returns file metadata including title, extension,
        size, and the latest ContentVersion ID (which can be used with
        salesforce_download_file to retrieve the actual content).

        Args:
            record_id: The parent record ID (e.g., Account, Opportunity, Contract ID)

        Returns:
            Dict with total_files count and files list containing
            content_document_id, title, file_extension, content_size,
            and latest_version_id for each file
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_record_files(record_id)

    # ==================== Approval Tools ====================

    async def salesforce_get_approval_history(
        self,
        record_id: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Get the approval process history for a Salesforce record.

        Queries ProcessInstance and related StepsAndWorkitems to retrieve
        the complete approval history for any record that has been submitted
        for approval (e.g., Contract, Opportunity, Quote).

        Args:
            record_id: The target record ID to get approval history for

        Returns:
            Dict with total_instances count and instances list, each containing
            id, status, created_date, completed_date, last_actor_name, and
            steps (with step_status, comments, actor_name, original_actor_name)
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_approval_history(record_id)

    async def salesforce_submit_approval(
        self,
        record_id: str,
        comments: str = "",
        submitter_id: str = "",
        next_approver_ids: list[str] | None = None,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Submit a record for approval.

        Initiates the approval process configured in Setup for the given record.
        Use salesforce_get_approval_history to check the result after submission.

        Args:
            record_id: The record ID to submit for approval (e.g., Opportunity, Contract)
            comments: Optional submission comments for the approver
            submitter_id: Optional submitter user ID (defaults to current user)
            next_approver_ids: Optional list of next approver user IDs

        Returns:
            Approval submission result with actorId, entityId, instanceId,
            instanceStatus, and newWorkitemIds
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.submit_approval(record_id, comments, submitter_id, next_approver_ids)

    async def salesforce_approve_reject(
        self,
        workitem_id: str,
        action: str,
        comments: str = "",
        actor_id: str = "",
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """Approve or reject a pending approval request.

        Processes a pending work item from the approval queue.
        Use salesforce_get_pending_approvals to find workitem IDs first.

        Args:
            workitem_id: The ProcessInstanceWorkitem ID to act on
            action: "Approve" or "Reject"
            comments: Optional comments explaining the decision
            actor_id: Optional actor user ID (defaults to current user)

        Returns:
            Approval action result with actorId, entityId, instanceId,
            instanceStatus, and newWorkitemIds
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.approve_reject(workitem_id, action, comments, actor_id)

    async def salesforce_get_pending_approvals(
        self,
        user_id: str = "",
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any]:
        """List pending approval requests assigned to a user.

        Queries ProcessInstanceWorkitem to find items awaiting approval.
        If user_id is not specified, returns all pending items visible
        to the current user.

        Args:
            user_id: Optional user ID to filter by assignee

        Returns:
            Dict with total_items count and items list containing workitem_id,
            target_object_id, target_object_name, target_object_type, status,
            created_date, and actor_name
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.get_pending_approvals(user_id)

    # ==================== Bulk API Tools ====================

    async def salesforce_bulk_query(
        self,
        sobject: str,
        soql: str,
        *,
        tool_context: ToolContext,
        credential: AuthCredential | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Execute a bulk SOQL query for large datasets (10,000+ records).

        Use this instead of salesforce_query when you expect a very large
        result set that would exceed standard query limits.

        Args:
            sobject: SObject type name (e.g., "Account", "Contact")
            soql: SOQL query string

        Returns:
            List of all matching records
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Bulk insert multiple records at once.

        Use this instead of salesforce_create_record when creating
        200 or more records for better performance.

        Args:
            sobject: SObject type name
            records: List of record data dictionaries

        Returns:
            List of results for each record with success, id, and errors
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Bulk update multiple records at once.

        Use this instead of salesforce_update_record when updating
        200 or more records for better performance.

        Args:
            sobject: SObject type name
            records: List of record data with Id field included in each record

        Returns:
            List of results for each record with success, id, and errors
        """
        client = await self._get_client(tool_context, credential)
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
        credential: AuthCredential | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Bulk delete multiple records at once. Confirm with the user
        before executing as this action is irreversible.

        Use this instead of salesforce_delete_record when deleting
        200 or more records for better performance.

        Args:
            sobject: SObject type name
            record_ids: List of record IDs to delete

        Returns:
            List of results for each record with success, id, and errors
        """
        client = await self._get_client(tool_context, credential)
        if error := self._check_auth(client):
            return error
        ops = SalesforceOperations(cast(Salesforce, client))
        return ops.bulk_delete(sobject, record_ids)
