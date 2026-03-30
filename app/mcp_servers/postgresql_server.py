"""
MCP Server for PostgreSQL
Connects via host/port/user/password/dbname.
Extracts schemas, tables, columns, views, indexes, and foreign keys.
Uses psycopg2 for database connectivity.
"""
from typing import Optional


class PostgreSQLMCPServer:
    """MCP Server to connect and extract metadata from PostgreSQL databases"""

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.conn = None
        self.connected = False

    def connect(self) -> bool:
        """Connect to PostgreSQL database"""
        try:
            import psycopg2
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10,
            )
            self.conn.autocommit = True
            # Test connection
            with self.conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
            print(f"✅ Connected to PostgreSQL: {version[:50]}")
            self.connected = True
            return True
        except Exception as e:
            print(f"❌ Failed to connect to PostgreSQL: {e}")
            self.connected = False
            return False

    def _query(self, sql: str, params=None) -> list[dict]:
        """Execute a query and return results as list of dicts"""
        if not self.connected or not self.conn:
            raise Exception("Not connected to PostgreSQL")
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Query error: {e}")
            return []

    def get_schemas(self) -> list[dict]:
        """List all user schemas (excluding system schemas)"""
        sql = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY schema_name
        """
        return self._query(sql)

    def get_tables(self, schema: str = "public") -> list[dict]:
        """List all tables in a schema"""
        sql = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
        """
        return self._query(sql, (schema,))

    def get_columns(self, schema: str, table_name: str) -> list[dict]:
        """Get columns and types for a specific table"""
        sql = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        return self._query(sql, (schema, table_name))

    def get_foreign_keys(self, schema: str = "public") -> list[dict]:
        """Get all foreign key relationships in a schema"""
        sql = """
            SELECT
                tc.constraint_name,
                tc.table_name AS source_table,
                kcu.column_name AS source_column,
                ccu.table_name AS target_table,
                ccu.column_name AS target_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
            ORDER BY tc.table_name
        """
        return self._query(sql, (schema,))

    def get_indexes(self, schema: str = "public") -> list[dict]:
        """Get all indexes in a schema"""
        sql = """
            SELECT
                indexname AS index_name,
                tablename AS table_name,
                indexdef AS definition
            FROM pg_indexes
            WHERE schemaname = %s
            ORDER BY tablename, indexname
        """
        return self._query(sql, (schema,))

    def get_views(self, schema: str = "public") -> list[dict]:
        """Get all views in a schema"""
        sql = """
            SELECT table_name AS view_name, view_definition
            FROM information_schema.views
            WHERE table_schema = %s
            ORDER BY table_name
        """
        return self._query(sql, (schema,))

    def get_row_counts(self, schema: str = "public") -> list[dict]:
        """Get estimated row counts for all tables in a schema"""
        sql = """
            SELECT
                relname AS table_name,
                n_live_tup AS estimated_rows
            FROM pg_stat_user_tables
            WHERE schemaname = %s
            ORDER BY n_live_tup DESC
        """
        return self._query(sql, (schema,))

    def get_schema_metadata(self, schema: str = "public") -> dict:
        """Get full metadata for a schema (tables + columns + FKs + views)"""
        if not self.connected:
            raise Exception("Not connected to PostgreSQL")
        
        tables = self.get_tables(schema)
        tables_with_columns = []
        for t in tables[:30]:  # Limit to 30 tables
            cols = self.get_columns(schema, t["table_name"])
            tables_with_columns.append({
                "table_name": t["table_name"],
                "table_type": t["table_type"],
                "columns": cols,
            })

        foreign_keys = self.get_foreign_keys(schema)
        views = self.get_views(schema)
        row_counts = self.get_row_counts(schema)

        return {
            "database": self.database,
            "schema": schema,
            "tables_count": len(tables),
            "tables": tables_with_columns,
            "foreign_keys": foreign_keys,
            "views": [{"name": v["view_name"], "definition": v["view_definition"][:500]} for v in views[:10]],
            "row_counts": row_counts,
        }
