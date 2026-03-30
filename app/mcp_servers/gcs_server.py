"""
MCP Server for Google Cloud Storage
Connects via service account JSON credentials.
Lists buckets, blobs, detects file types, reads CSV/JSON headers.
Uses google-cloud-storage client library.
"""
from typing import Optional
import json
import io


class GCSMCPServer:
    """MCP Server to connect and extract metadata from Google Cloud Storage"""

    def __init__(self, service_account_json: dict):
        self.service_account_json = service_account_json
        self.client = None
        self.project_id = service_account_json.get("project_id", "")
        self.connected = False

    def connect(self) -> bool:
        """Connect to GCS using service account credentials"""
        try:
            from google.cloud import storage
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                self.service_account_json,
            )
            self.client = storage.Client(
                credentials=credentials,
                project=self.project_id,
            )
            # Test connection by listing buckets (limit 1)
            list(self.client.list_buckets(max_results=1))
            self.connected = True
            print(f"✅ Connected to GCS (project: {self.project_id})")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to GCS: {e}")
            self.connected = False
            return False

    def get_buckets(self) -> list[dict]:
        """List all buckets in the project"""
        if not self.connected:
            raise Exception("Not connected to GCS")
        try:
            buckets = []
            for bucket in self.client.list_buckets():
                buckets.append({
                    "name": bucket.name,
                    "location": bucket.location,
                    "storage_class": bucket.storage_class,
                    "created": bucket.time_created.isoformat() if bucket.time_created else None,
                })
            return buckets
        except Exception as e:
            print(f"❌ Error listing buckets: {e}")
            return []

    def get_blobs(self, bucket_name: str, prefix: str = "", max_results: int = 100) -> list[dict]:
        """List blobs (files) in a bucket with optional prefix filter"""
        if not self.connected:
            raise Exception("Not connected to GCS")
        try:
            bucket = self.client.bucket(bucket_name)
            blobs = []
            for blob in bucket.list_blobs(prefix=prefix or None, max_results=max_results):
                blobs.append({
                    "name": blob.name,
                    "size": blob.size,
                    "content_type": blob.content_type,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "file_type": self._detect_file_type(blob.name),
                })
            return blobs
        except Exception as e:
            print(f"❌ Error listing blobs: {e}")
            return []

    def _detect_file_type(self, filename: str) -> str:
        """Detect file type from extension"""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        type_map = {
            "csv": "CSV", "tsv": "TSV", "json": "JSON", "jsonl": "JSONL",
            "parquet": "Parquet", "avro": "Avro", "orc": "ORC",
            "xlsx": "Excel", "xls": "Excel",
            "sql": "SQL", "py": "Python", "yaml": "YAML", "yml": "YAML",
            "xml": "XML", "txt": "Text", "gz": "Gzip", "zip": "Zip",
        }
        return type_map.get(ext, "Other")

    def read_csv_header(self, bucket_name: str, blob_name: str) -> dict:
        """Read the header (first few lines) of a CSV file"""
        if not self.connected:
            raise Exception("Not connected to GCS")
        try:
            import csv
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            # Download first 10KB only
            content = blob.download_as_text(end=10240)
            reader = csv.reader(io.StringIO(content))
            headers = next(reader, [])
            sample_rows = []
            for i, row in enumerate(reader):
                if i >= 3:
                    break
                sample_rows.append(row)
            return {
                "blob_name": blob_name,
                "headers": headers,
                "sample_rows": sample_rows,
                "columns_count": len(headers),
            }
        except Exception as e:
            print(f"❌ Error reading CSV header: {e}")
            return {}

    def read_json_structure(self, bucket_name: str, blob_name: str) -> dict:
        """Read the structure of a JSON file (keys and types)"""
        if not self.connected:
            raise Exception("Not connected to GCS")
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            content = blob.download_as_text(end=51200)  # First 50KB
            data = json.loads(content)

            def extract_structure(obj, depth=0):
                if depth > 3:
                    return "..."
                if isinstance(obj, dict):
                    return {k: extract_structure(v, depth + 1) for k, v in list(obj.items())[:20]}
                elif isinstance(obj, list):
                    if obj:
                        return [extract_structure(obj[0], depth + 1)]
                    return []
                else:
                    return type(obj).__name__

            structure = extract_structure(data)
            return {
                "blob_name": blob_name,
                "structure": structure,
                "type": "array" if isinstance(data, list) else "object",
                "records_count": len(data) if isinstance(data, list) else 1,
            }
        except Exception as e:
            print(f"❌ Error reading JSON structure: {e}")
            return {}

    def get_bucket_metadata(self, bucket_name: str, prefix: str = "") -> dict:
        """Get summary metadata for a bucket"""
        if not self.connected:
            raise Exception("Not connected to GCS")
        blobs = self.get_blobs(bucket_name, prefix=prefix, max_results=200)

        # Count by type
        type_counts = {}
        total_size = 0
        for b in blobs:
            ft = b["file_type"]
            type_counts[ft] = type_counts.get(ft, 0) + 1
            total_size += b.get("size", 0) or 0

        return {
            "bucket_name": bucket_name,
            "prefix": prefix,
            "total_files": len(blobs),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_types": type_counts,
            "files": blobs[:50],  # Return first 50
        }
