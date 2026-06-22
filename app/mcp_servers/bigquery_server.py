"""
MCP Server for BigQuery
Connects via service account JSON credentials.
Extracts datasets, tables, columns, views, and preview rows.
Uses google-cloud-bigquery client library.
"""
import logging
from typing import Optional
import json

logger = logging.getLogger(__name__)


class BigQueryMCPServer:
    """MCP Server to connect and extract metadata from Google BigQuery"""

    def __init__(self, service_account_json: dict):
        self.service_account_json = service_account_json
        self.client = None
        self.project_id = service_account_json.get("project_id", "")
        self.connected = False

    def connect(self) -> bool:
        """Connect to BigQuery using service account credentials"""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                self.service_account_json,
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
            )
            self.client = bigquery.Client(
                credentials=credentials,
                project=self.project_id,
            )
            # Test connection by listing datasets (limit 1)
            list(self.client.list_datasets(max_results=1))
            self.connected = True
            logger.info("Connected to BigQuery (project: %s)", self.project_id)
            return True
        except Exception as e:
            logger.error("Failed to connect to BigQuery: %s", e)
            self.connected = False
            return False

    def get_datasets(self) -> list[dict]:
        """List all datasets in the project"""
        if not self.connected:
            raise Exception("Not connected to BigQuery")
        try:
            datasets = []
            for ds in self.client.list_datasets():
                datasets.append({
                    "dataset_id": ds.dataset_id,
                    "full_id": ds.full_dataset_id,
                    "project": ds.project,
                })
            return datasets
        except Exception as e:
            logger.error("Error listing datasets: %s", e)
            return []

    def get_tables(self, dataset_id: str) -> list[dict]:
        """List all tables in a dataset"""
        if not self.connected:
            raise Exception("Not connected to BigQuery")
        try:
            tables = []
            dataset_ref = self.client.dataset(dataset_id)
            for table in self.client.list_tables(dataset_ref):
                tables.append({
                    "table_id": table.table_id,
                    "table_type": table.table_type,  # TABLE, VIEW, EXTERNAL
                    "full_id": f"{dataset_id}.{table.table_id}",
                })
            return tables
        except Exception as e:
            logger.error("Error listing tables: %s", e)
            return []

    def get_table_schema(self, dataset_id: str, table_id: str) -> dict:
        """Get schema (columns, types) for a specific table"""
        if not self.connected:
            raise Exception("Not connected to BigQuery")
        try:
            table_ref = self.client.dataset(dataset_id).table(table_id)
            table = self.client.get_table(table_ref)
            columns = []
            for field in table.schema:
                columns.append({
                    "name": field.name,
                    "type": field.field_type,
                    "mode": field.mode,  # NULLABLE, REQUIRED, REPEATED
                    "description": field.description or "",
                })
            return {
                "dataset_id": dataset_id,
                "table_id": table_id,
                "table_type": table.table_type,
                "num_rows": table.num_rows,
                "num_bytes": table.num_bytes,
                "created": table.created.isoformat() if table.created else None,
                "modified": table.modified.isoformat() if table.modified else None,
                "columns": columns,
            }
        except Exception as e:
            logger.error("Error getting table schema: %s", e)
            return {}

    def preview_rows(self, dataset_id: str, table_id: str, max_rows: int = 5) -> list[dict]:
        """Preview first N rows of a table"""
        if not self.connected:
            raise Exception("Not connected to BigQuery")
        try:
            query = f"SELECT * FROM `{self.project_id}.{dataset_id}.{table_id}` LIMIT {max_rows}"
            result = self.client.query(query).result()
            rows = []
            for row in result:
                rows.append(dict(row))
            return rows
        except Exception as e:
            logger.error("Error previewing rows: %s", e)
            return []

    def get_dataset_metadata(self, dataset_id: str) -> dict:
        """Get full metadata for a dataset (tables + schemas)"""
        if not self.connected:
            raise Exception("Not connected to BigQuery")
        tables = self.get_tables(dataset_id)
        tables_with_schema = []
        for t in tables[:20]:  # Limit to 20 tables
            schema = self.get_table_schema(dataset_id, t["table_id"])
            tables_with_schema.append(schema)
        return {
            "project_id": self.project_id,
            "dataset_id": dataset_id,
            "tables_count": len(tables),
            "tables": tables_with_schema,
        }
