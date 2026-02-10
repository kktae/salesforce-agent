"""Salesforce operations wrapper using simple-salesforce."""

import base64
import logging
from functools import wraps
from typing import Any, Optional

from simple_salesforce.api import Salesforce
from simple_salesforce.exceptions import SalesforceError

logger = logging.getLogger(__name__)


def _handle_salesforce_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SalesforceError as e:
            logger.warning(
                "Salesforce API error in %s: [%s] %s",
                func.__name__,
                type(e).__name__,
                e,
            )
            content = e.content
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            return {
                "error": str(e),
                "error_code": e.status,
                "details": content,
            }

    return wrapper


class SalesforceOperations:
    """
    Wrapper class for Salesforce operations using simple-salesforce.

    Provides a clean interface for all Salesforce API operations
    including queries, CRUD, metadata, and bulk operations.
    """

    def __init__(self, client: Salesforce):
        """
        Initialize with a Salesforce client.

        Args:
            client: Authenticated simple_salesforce.Salesforce instance
        """
        self.client = client

    # ==================== Query Operations ====================

    @_handle_salesforce_errors
    def query(self, soql: str, include_deleted: bool = False) -> dict[str, Any]:
        """
        Execute a SOQL query.

        Args:
            soql: SOQL query string
            include_deleted: If True, includes deleted/archived records

        Returns:
            Query results with totalSize, done, and records
        """
        if include_deleted:
            return self.client.query_all(soql)
        return self.client.query(soql)

    @_handle_salesforce_errors
    def query_all(self, soql: str) -> dict[str, Any]:
        """
        Execute a SOQL query including deleted/archived records.

        Args:
            soql: SOQL query string

        Returns:
            Query results with totalSize, done, and records
        """
        return self.client.query_all(soql)

    @_handle_salesforce_errors
    def query_more(self, next_records_url: str) -> dict[str, Any]:
        """
        Fetch more results for a paginated query.

        Args:
            next_records_url: The nextRecordsUrl from a previous query result

        Returns:
            Additional query results
        """
        return self.client.query_more(next_records_url, identifier_is_url=True)

    @_handle_salesforce_errors
    def search(self, sosl: str) -> dict[str, Any]:
        """
        Execute a SOSL search.

        Args:
            sosl: SOSL search string

        Returns:
            Search results
        """
        return self.client.search(sosl)

    # ==================== Record CRUD Operations ====================

    @_handle_salesforce_errors
    def get_record(
        self,
        sobject: str,
        record_id: str,
        fields: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Get a record by ID.

        Args:
            sobject: SObject type (e.g., 'Account', 'Contact')
            record_id: Salesforce record ID
            fields: Optional list of fields to retrieve

        Returns:
            Record data
        """
        sobject_type = getattr(self.client, sobject)
        if fields:
            return sobject_type.get(record_id, fields=fields)
        return sobject_type.get(record_id)

    @_handle_salesforce_errors
    def create_record(self, sobject: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new record.

        Args:
            sobject: SObject type
            data: Record field data

        Returns:
            Result with id, success, and errors
        """
        sobject_type = getattr(self.client, sobject)
        return sobject_type.create(data)

    @_handle_salesforce_errors
    def update_record(
        self,
        sobject: str,
        record_id: str,
        data: dict[str, Any],
    ) -> int:
        """
        Update an existing record.

        Args:
            sobject: SObject type
            record_id: Salesforce record ID
            data: Field data to update

        Returns:
            HTTP status code (204 for success)
        """
        sobject_type = getattr(self.client, sobject)
        return sobject_type.update(record_id, data)

    @_handle_salesforce_errors
    def delete_record(self, sobject: str, record_id: str) -> int:
        """
        Delete a record.

        Args:
            sobject: SObject type
            record_id: Salesforce record ID

        Returns:
            HTTP status code (204 for success)
        """
        sobject_type = getattr(self.client, sobject)
        return sobject_type.delete(record_id)

    @_handle_salesforce_errors
    def upsert_record(
        self,
        sobject: str,
        external_id_field: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Upsert a record using an external ID.

        Args:
            sobject: SObject type
            external_id_field: External ID field name
            data: Record data (must include the external ID field)

        Returns:
            Result with id, success, and created flag
        """
        sobject_type = getattr(self.client, sobject)
        external_id_value = data.get(external_id_field)
        return sobject_type.upsert(
            f"{external_id_field}/{external_id_value}",
            data,
        )

    # ==================== Metadata Operations ====================

    @_handle_salesforce_errors
    def describe_object(self, sobject: str) -> dict[str, Any]:
        """
        Get full metadata for an SObject.

        Args:
            sobject: SObject type

        Returns:
            Complete object metadata including fields, record types, etc.
        """
        sobject_type = getattr(self.client, sobject)
        return sobject_type.describe()

    @_handle_salesforce_errors
    def list_objects(self) -> dict[str, Any] | None:
        """
        List all available SObjects.

        Returns:
            Dict with sobjects list containing name, label, etc.
        """
        return self.client.describe()

    @_handle_salesforce_errors
    def get_object_fields(self, sobject: str) -> list[dict[str, Any]] | dict[str, Any]:
        """
        Get field information for an SObject.

        Args:
            sobject: SObject type

        Returns:
            List of field metadata dictionaries
        """
        description = self.describe_object(sobject)
        if isinstance(description, dict) and "error" in description:
            return description
        return description.get("fields", [])

    # ==================== Currency Operations ====================

    @_handle_salesforce_errors
    def get_currency_config(self) -> dict[str, Any]:
        """
        Get the org's Multi-Currency configuration.

        Queries CurrencyType and DatedConversionRate to determine:
        - Whether Multi-Currency is enabled
        - The corporate currency
        - Active currencies with conversion rates
        - Whether Advanced Currency Management (ACM) is enabled

        Returns:
            Currency configuration dict with multi_currency_enabled,
            corporate_currency, currencies, advanced_currency_management,
            and dated_rates.
        """
        result: dict[str, Any] = {
            "multi_currency_enabled": False,
            "corporate_currency": None,
            "currencies": [],
            "advanced_currency_management": False,
            "dated_rates": [],
        }

        # Query active currencies — fails if Multi-Currency is not enabled
        try:
            currency_response = self.client.query(
                "SELECT IsoCode, ConversionRate, DecimalPlaces, IsCorporate, IsActive "
                "FROM CurrencyType WHERE IsActive = true ORDER BY IsoCode"
            )
        except Exception:
            logger.info("CurrencyType query failed — Multi-Currency is not enabled.")
            return result

        result["multi_currency_enabled"] = True
        currencies = []
        for record in currency_response.get("records", []):
            entry = {
                "iso_code": record["IsoCode"],
                "conversion_rate": record["ConversionRate"],
                "decimal_places": record["DecimalPlaces"],
                "is_corporate": record["IsCorporate"],
            }
            currencies.append(entry)
            if record["IsCorporate"]:
                result["corporate_currency"] = record["IsoCode"]
        result["currencies"] = currencies

        # Query dated conversion rates — fails if ACM is not enabled
        try:
            dated_response = self.client.query(
                "SELECT IsoCode, ConversionRate, StartDate, NextStartDate "
                "FROM DatedConversionRate "
                "WHERE StartDate <= TODAY AND NextStartDate > TODAY "
                "ORDER BY IsoCode"
            )
            result["advanced_currency_management"] = True
            dated_rates = []
            for record in dated_response.get("records", []):
                dated_rates.append(
                    {
                        "iso_code": record["IsoCode"],
                        "conversion_rate": record["ConversionRate"],
                        "start_date": record["StartDate"],
                        "next_start_date": record["NextStartDate"],
                    }
                )
            result["dated_rates"] = dated_rates
        except Exception:
            logger.info(
                "DatedConversionRate query failed — Advanced Currency Management is not enabled."
            )

        return result

    # ==================== Report Operations ====================

    @_handle_salesforce_errors
    def list_reports(self) -> list[dict[str, Any]]:
        """
        List recently viewed reports (up to 200).

        Returns:
            List of report summary dicts with id, name, url, etc.
        """
        result = self.client.restful("analytics/reports", method="GET")
        return result if result is not None else []

    @_handle_salesforce_errors
    def run_report(
        self,
        report_id: str,
        filters: Optional[list[dict[str, Any]]] = None,
        include_details: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a report synchronously.

        Args:
            report_id: The 15/18-character report ID
            filters: Optional list of dynamic filters to apply.
                     Each filter dict should have column, operator, value keys.
            include_details: If True, include detail rows in results

        Returns:
            Report execution result with reportMetadata, factMap, etc.
        """
        params = {"includeDetails": "true" if include_details else "false"}
        if filters:
            result = self.client.restful(
                f"analytics/reports/{report_id}",
                method="POST",
                params=params,
                json={"reportMetadata": {"reportFilters": filters}},
            )
        else:
            result = self.client.restful(
                f"analytics/reports/{report_id}",
                method="GET",
                params=params,
            )
        return result if result is not None else {}

    @_handle_salesforce_errors
    def describe_report(self, report_id: str) -> dict[str, Any]:
        """
        Get report metadata (columns, filters, groupings, report type, etc.).

        Args:
            report_id: The 15/18-character report ID

        Returns:
            Report metadata dict with reportMetadata, reportTypeMetadata, etc.
        """
        result = self.client.restful(
            f"analytics/reports/{report_id}/describe", method="GET"
        )
        return result if result is not None else {}

    @_handle_salesforce_errors
    def run_report_async(
        self,
        report_id: str,
        filters: Optional[list[dict[str, Any]]] = None,
        include_details: bool = True,
    ) -> dict[str, Any]:
        """
        Request an asynchronous report execution.

        Args:
            report_id: The 15/18-character report ID
            filters: Optional list of dynamic filters to apply
            include_details: If True, include detail rows in results

        Returns:
            Instance info dict containing the instance id for polling
        """
        params = {"includeDetails": "true" if include_details else "false"}
        json_body: dict[str, Any] | None = None
        if filters:
            json_body = {"reportMetadata": {"reportFilters": filters}}
        result = self.client.restful(
            f"analytics/reports/{report_id}/instances",
            method="POST",
            params=params,
            json=json_body,
        )
        return result if result is not None else {}

    @_handle_salesforce_errors
    def get_report_instance(self, report_id: str, instance_id: str) -> dict[str, Any]:
        """
        Get the result of an asynchronous report execution.

        Args:
            report_id: The 15/18-character report ID
            instance_id: The instance ID returned by run_report_async

        Returns:
            Report execution result (same structure as run_report)
        """
        result = self.client.restful(
            f"analytics/reports/{report_id}/instances/{instance_id}",
            method="GET",
        )
        return result if result is not None else {}

    # ==================== File & Content Operations ====================

    @_handle_salesforce_errors
    def download_file(
        self,
        record_id: str,
        sobject: str = "ContentVersion",
        blob_field: str = "VersionData",
    ) -> dict[str, Any]:
        """
        Download binary content from a Salesforce record's blob field.

        Args:
            record_id: ContentVersion ID or Attachment ID
            sobject: 'ContentVersion' or 'Attachment'
            blob_field: Blob field name ('VersionData' for ContentVersion, 'Body' for Attachment)

        Returns:
            Dict with base64-encoded content, content_type, and file metadata
        """
        sobject_type = getattr(self.client, sobject)
        raw_bytes = sobject_type.get_base64(record_id, base64_field=blob_field)

        # Fetch metadata for the file
        metadata: dict[str, Any] = {}
        if sobject == "ContentVersion":
            record = sobject_type.get(record_id)
            metadata = {
                "title": record.get("Title"),
                "file_extension": record.get("FileExtension"),
                "content_size": record.get("ContentSize"),
                "version_number": record.get("VersionNumber"),
                "content_document_id": record.get("ContentDocumentId"),
            }
        elif sobject == "Attachment":
            record = sobject_type.get(record_id)
            metadata = {
                "name": record.get("Name"),
                "content_type": record.get("ContentType"),
                "body_length": record.get("BodyLength"),
                "parent_id": record.get("ParentId"),
            }

        return {
            "record_id": record_id,
            "sobject": sobject,
            "content_base64": base64.b64encode(raw_bytes).decode("ascii"),
            "size_bytes": len(raw_bytes),
            "metadata": metadata,
        }

    @_handle_salesforce_errors
    def get_record_files(self, record_id: str) -> dict[str, Any]:
        """
        Get files attached to a Salesforce record via ContentDocumentLink.

        Args:
            record_id: The parent record ID (Account, Opportunity, Contract, etc.)

        Returns:
            Dict with list of file metadata (ContentDocument info, latest version info)
        """
        soql = (
            "SELECT ContentDocumentId, "
            "ContentDocument.Title, "
            "ContentDocument.FileExtension, "
            "ContentDocument.ContentSize, "
            "ContentDocument.LatestPublishedVersionId "
            "FROM ContentDocumentLink "
            f"WHERE LinkedEntityId = '{record_id}'"
        )
        result = self.client.query(soql)
        files = []
        for record in result.get("records", []):
            doc = record.get("ContentDocument") or {}
            files.append(
                {
                    "content_document_id": record.get("ContentDocumentId"),
                    "title": doc.get("Title"),
                    "file_extension": doc.get("FileExtension"),
                    "content_size": doc.get("ContentSize"),
                    "latest_version_id": doc.get("LatestPublishedVersionId"),
                }
            )
        return {
            "record_id": record_id,
            "total_files": len(files),
            "files": files,
        }

    # ==================== Approval Operations ====================

    @_handle_salesforce_errors
    def get_approval_history(self, record_id: str) -> dict[str, Any]:
        """
        Get the approval process history for a Salesforce record.

        Args:
            record_id: The target record ID (Contract, Opportunity, etc.)

        Returns:
            Dict with list of approval instances including steps, actors, and comments
        """
        soql = (
            "SELECT Id, Status, CreatedDate, CompletedDate, LastActor.Name, "
            "(SELECT Id, StepStatus, Comments, Actor.Name, OriginalActor.Name, "
            "CreatedDate FROM StepsAndWorkitems ORDER BY CreatedDate) "
            "FROM ProcessInstance "
            f"WHERE TargetObjectId = '{record_id}' "
            "ORDER BY CreatedDate DESC"
        )
        result = self.client.query(soql)
        instances = []
        for record in result.get("records", []):
            last_actor = record.get("LastActor") or {}
            steps_data = record.get("StepsAndWorkitems") or {}
            steps = []
            for step in steps_data.get("records", []):
                actor = step.get("Actor") or {}
                original_actor = step.get("OriginalActor") or {}
                steps.append(
                    {
                        "id": step.get("Id"),
                        "step_status": step.get("StepStatus"),
                        "comments": step.get("Comments"),
                        "actor_name": actor.get("Name"),
                        "original_actor_name": original_actor.get("Name"),
                        "created_date": step.get("CreatedDate"),
                    }
                )
            instances.append(
                {
                    "id": record.get("Id"),
                    "status": record.get("Status"),
                    "created_date": record.get("CreatedDate"),
                    "completed_date": record.get("CompletedDate"),
                    "last_actor_name": last_actor.get("Name"),
                    "steps": steps,
                }
            )
        return {
            "record_id": record_id,
            "total_instances": len(instances),
            "instances": instances,
        }

    # ==================== Identity Operations ====================

    @_handle_salesforce_errors
    def get_user_identity(self) -> dict[str, Any]:
        """
        Get the current authenticated user's identity information.

        Calls the Salesforce OpenID Connect UserInfo endpoint
        (/services/oauth2/userinfo) to retrieve profile information
        for the user associated with the current access token.

        Returns:
            User identity dict containing user_id, organization_id,
            name, email, preferred_username, zoneinfo, locale, user_type, etc.
        """
        result = self.client.oauth2("userinfo")
        if result is None:
            return {"error": "UserInfo endpoint returned no data."}
        return result

    # ==================== Bulk API Operations ====================

    @_handle_salesforce_errors
    def bulk_query(self, sobject: str, soql: str) -> list[dict[str, Any]]:
        """
        Execute a bulk query for large datasets.

        Args:
            sobject: SObject type
            soql: SOQL query string

        Returns:
            List of all records
        """
        return self.client.bulk.__getattr__(sobject).query(soql)  # type: ignore[attr-defined]

    @_handle_salesforce_errors
    def bulk_insert(
        self,
        sobject: str,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Bulk insert multiple records.

        Args:
            sobject: SObject type
            records: List of record data dictionaries

        Returns:
            List of results with success/error for each record
        """
        return self.client.bulk.__getattr__(sobject).insert(records)  # type: ignore[attr-defined]

    @_handle_salesforce_errors
    def bulk_update(
        self,
        sobject: str,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Bulk update multiple records.

        Args:
            sobject: SObject type
            records: List of record data (must include Id field)

        Returns:
            List of results with success/error for each record
        """
        return self.client.bulk.__getattr__(sobject).update(records)  # type: ignore[attr-defined]

    @_handle_salesforce_errors
    def bulk_delete(
        self,
        sobject: str,
        record_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Bulk delete multiple records.

        Args:
            sobject: SObject type
            record_ids: List of record IDs to delete

        Returns:
            List of results with success/error for each record
        """
        # Convert IDs to the format expected by bulk delete
        records = [{"Id": rid} for rid in record_ids]
        return self.client.bulk.__getattr__(sobject).delete(records)  # type: ignore[attr-defined]
