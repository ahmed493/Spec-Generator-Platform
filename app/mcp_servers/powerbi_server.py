"""
MCP Server for Power BI
Connects via Azure AD Service Principal or Master User authentication.
Extracts workspaces, datasets, tables, columns, DAX measures, and reports.
Uses the Power BI REST API: https://learn.microsoft.com/en-us/rest/api/power-bi/
"""
import requests
from typing import Optional


class PowerBIMCPServer:
    """MCP Server to connect and extract metadata from Power BI"""

    AUTHORITY_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    API_BASE = "https://api.powerbi.com/v1.0/myorg"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: Optional[str] = None
        self.connected = False
        self.user_info: dict = {}

    def connect(self) -> bool:
        """Authenticate with Azure AD using client credentials (Service Principal)"""
        try:
            url = self.AUTHORITY_URL.format(tenant_id=self.tenant_id)
            payload = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://analysis.windows.net/powerbi/api/.default",
            }
            resp = requests.post(url, data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self.connected = True

            # Test connection by listing workspaces
            test = self._get("/groups", params={"$top": 1})
            if test is not None:
                print(f" Connected to Power BI (tenant: {self.tenant_id})")
                return True
            else:
                self.connected = False
                return False
        except Exception as e:
            print(f" Failed to connect to Power BI: {e}")
            self.connected = False
            return False

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make authenticated GET request to Power BI REST API"""
        if not self.access_token:
            raise Exception("Not connected to Power BI")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.API_BASE}{endpoint}"
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f" Power BI API error on {endpoint}: {e}")
            return None

    # ============== WORKSPACES ==============

    def get_workspaces(self) -> list[dict]:
        """List all workspaces (groups) the service principal has access to"""
        data = self._get("/groups")
        if not data:
            return []
        return [
            {
                "id": ws["id"],
                "name": ws["name"],
                "type": ws.get("type", "Workspace"),
                "state": ws.get("state", "Active"),
                "isOnDedicatedCapacity": ws.get("isOnDedicatedCapacity", False),
            }
            for ws in data.get("value", [])
        ]

    # ============== DATASETS ==============

    def get_datasets(self, workspace_id: str) -> list[dict]:
        """List all datasets in a workspace"""
        data = self._get(f"/groups/{workspace_id}/datasets")
        if not data:
            return []
        return [
            {
                "id": ds["id"],
                "name": ds["name"],
                "configuredBy": ds.get("configuredBy", ""),
                "isRefreshable": ds.get("isRefreshable", False),
                "isOnPremGatewayRequired": ds.get("isOnPremGatewayRequired", False),
                "createdDate": ds.get("createdDate", ""),
            }
            for ds in data.get("value", [])
        ]

    def get_dataset_tables(self, workspace_id: str, dataset_id: str) -> list[dict]:
        """Get tables in a dataset (requires XMLA or push dataset)"""
        data = self._get(f"/groups/{workspace_id}/datasets/{dataset_id}/tables")
        if not data:
            return []
        return [
            {
                "name": tbl["name"],
                "columns": [
                    {
                        "name": col["name"],
                        "dataType": col.get("dataType", "Unknown"),
                        "isHidden": col.get("isHidden", False),
                    }
                    for col in tbl.get("columns", [])
                ],
                "measures": [
                    {
                        "name": m["name"],
                        "expression": m.get("expression", ""),
                    }
                    for m in tbl.get("measures", [])
                ],
            }
            for tbl in data.get("value", [])
        ]

    def get_dataset_datasources(self, workspace_id: str, dataset_id: str) -> list[dict]:
        """Get data sources connected to a dataset"""
        data = self._get(f"/groups/{workspace_id}/datasets/{dataset_id}/datasources")
        if not data:
            return []
        return [
            {
                "datasourceType": ds.get("datasourceType", "Unknown"),
                "connectionDetails": ds.get("connectionDetails", {}),
                "datasourceId": ds.get("datasourceId", ""),
                "gatewayId": ds.get("gatewayId", ""),
            }
            for ds in data.get("value", [])
        ]

    # ============== REPORTS ==============

    def get_reports(self, workspace_id: str) -> list[dict]:
        """List all reports in a workspace"""
        data = self._get(f"/groups/{workspace_id}/reports")
        if not data:
            return []
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "datasetId": r.get("datasetId", ""),
                "reportType": r.get("reportType", "PowerBIReport"),
                "webUrl": r.get("webUrl", ""),
            }
            for r in data.get("value", [])
        ]

    def get_report_pages(self, workspace_id: str, report_id: str) -> list[dict]:
        """Get pages of a report"""
        data = self._get(f"/groups/{workspace_id}/reports/{report_id}/pages")
        if not data:
            return []
        return [
            {
                "name": p["name"],
                "displayName": p.get("displayName", p["name"]),
                "order": p.get("order", 0),
            }
            for p in data.get("value", [])
        ]

    # ============== DATAFLOWS ==============

    def get_dataflows(self, workspace_id: str) -> list[dict]:
        """List dataflows in a workspace"""
        data = self._get(f"/groups/{workspace_id}/dataflows")
        if not data:
            return []
        return [
            {
                "objectId": df["objectId"],
                "name": df["name"],
                "description": df.get("description", ""),
                "configuredBy": df.get("configuredBy", ""),
            }
            for df in data.get("value", [])
        ]

    # ============== FULL METADATA ==============

    def get_workspace_metadata(self, workspace_id: str) -> dict:
        """Get comprehensive metadata for a workspace — datasets, reports, dataflows"""
        datasets = self.get_datasets(workspace_id)
        reports = self.get_reports(workspace_id)
        dataflows = self.get_dataflows(workspace_id)

        # Enrich datasets with tables & datasources
        for ds in datasets:
            ds["tables"] = self.get_dataset_tables(workspace_id, ds["id"])
            ds["datasources"] = self.get_dataset_datasources(workspace_id, ds["id"])

        # Enrich reports with pages
        for r in reports:
            r["pages"] = self.get_report_pages(workspace_id, r["id"])

        return {
            "workspace_id": workspace_id,
            "datasets": datasets,
            "reports": reports,
            "dataflows": dataflows,
            "summary": {
                "total_datasets": len(datasets),
                "total_reports": len(reports),
                "total_dataflows": len(dataflows),
                "total_tables": sum(len(ds.get("tables", [])) for ds in datasets),
            },
        }
