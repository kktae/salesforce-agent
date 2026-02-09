"""Salesforce operations wrapper using simple-salesforce."""

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
