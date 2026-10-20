import os
import urllib.parse
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


class DatabaseManager:
    """Manages database connection, schema inspection, and query execution."""

    def __init__(
        self,
        host: str | None = None,
        port: str | int | None = None,
        database: str | None = None,
        username: str | None = None,
        raw_password: str | None = None,
        db_url: str | None = None,
    ):
        if db_url:
            self.db_url = db_url
        else:
            host = host or os.getenv("DB_HOST", "localhost")
            port = str(port or os.getenv("DB_PORT", "3306"))
            database = database or os.getenv("DB_NAME", "RAG")
            username = username or os.getenv("DB_USER", "loco")
            raw_password = raw_password or os.getenv("DB_PASSWORD", "erRor100@23")
            password = urllib.parse.quote_plus(str(raw_password))
            self.db_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"

        self.engine = create_engine(self.db_url, pool_pre_ping=True)
        self.inspector = inspect(self.engine)

    def test_connection(self) -> tuple[bool, str]:
        """Verifies database connectivity."""
        try:
            with self.engine.connect() as con:
                con.execute(text("SELECT 1"))
            return True, "Database connection successful."
        except Exception as e:
            return False, f"Database connection failed: {e}"

    def get_table_schema(self, target_tables: list[str], verbose: bool = False) -> str:
        """Returns readable table schemas for target tables."""
        schema_des = "You have access to the following SQL table(s):\n\n"
        for t_name in target_tables:
            try:
                columns_info = [(col["name"], str(col["type"])) for col in self.inspector.get_columns(t_name)]
                schema_des += f"Table: '{t_name}'\nColumns:\n"
                schema_des += "\n".join([f" - {name}: {col_type}" for name, col_type in columns_info])
                schema_des += "\n\n"
            except Exception as e:
                schema_des += f"Table '{t_name}': Warning: Could not read schema ({e})\n\n"

        if verbose:
            print(schema_des)
        return schema_des

    def get_table_relationships(self, target_tables: list[str], verbose: bool = False) -> str:
        """Returns a description of foreign key and logical relationships between the

        given tables so the agent knows how to JOIN them correctly.
        """
        relationships_des = "Relationships between tables (use these for JOINs):\n"
        found_any = False

        # 1. Physical foreign keys defined in the database
        for t_name in target_tables:
            try:
                fks = self.inspector.get_foreign_keys(t_name)
                for fk in fks:
                    constrained_cols = ", ".join(fk["constrained_columns"])
                    referred_table = fk["referred_table"]
                    referred_cols = ", ".join(fk["referred_columns"])
                    # Use ASCII '->' instead of unicode arrow to avoid Windows cp1252 encoding issues
                    relationships_des += (
                        f" - {t_name}.{constrained_cols} -> {referred_table}.{referred_cols}\n"
                    )
                    found_any = True
            except Exception as e:
                relationships_des += f" - {t_name}: Error reading foreign keys: {e}\n"

        # 2. Known logical domain relationships (useful when foreign keys are not explicitly declared in DDL)
        logical_fks = [
            ("bookings", "CustomerID", "customers", "CustomerID"),
            ("bookings", "HotelID", "hotels", "HotelID"),
            ("bookings", "FlightID", "flights", "FlightID"),
            ("flights", "OriginCityID", "cities", "CityID"),
            ("flights", "DestinationCityID", "cities", "CityID"),
            ("hotels", "CityID", "cities", "CityID"),
            ("customers", "PreferredCityID", "cities", "CityID"),
        ]

        target_set = set(target_tables)
        for src_tab, src_col, ref_tab, ref_col in logical_fks:
            if src_tab in target_set and ref_tab in target_set:
                entry = f" - {src_tab}.{src_col} -> {ref_tab}.{ref_col}\n"
                if entry not in relationships_des:
                    relationships_des += entry
                    found_any = True

        if not found_any:
            relationships_des += " - No foreign key relationships found among the given tables.\n"

        if verbose:
            print(relationships_des)
        return relationships_des

    def execute_query(self, query: str) -> str:
        """Safely executes a SQL query and formats the result as human-readable text."""
        cleaned_query = query.strip().rstrip(";")
        if not cleaned_query:
            return "No query provided to execute."

        try:
            with self.engine.connect() as con:
                result = con.execute(text(cleaned_query))

                # Handle statements that do not return rows
                if not result.returns_rows:
                    return f"Query executed successfully. Rows affected: {result.rowcount}."

                columns = list(result.keys())
                rows = result.fetchall()

                if not rows:
                    return "No matching result was found in the database."

                # Single column, single row -> common scalar results (count, average, sum, name)
                if len(rows) == 1 and len(columns) == 1:
                    col_name = columns[0].lower()
                    return f"The {col_name} is {rows[0][0]}."

                # Multiple columns, single row
                if len(rows) == 1:
                    parts = [f"{col}: {val}" for col, val in zip(columns, rows[0])]
                    return "Result: " + ", ".join(parts) + "."

                # Multiple rows -> formatted summary (limit display to first 25 rows)
                preview_rows = rows[:25]
                line_items = [
                    ", ".join(f"{col}={val}" for col, val in zip(columns, row))
                    for row in preview_rows
                ]
                output = f"Found {len(rows)} matching rows: " + "; ".join(line_items)
                if len(rows) > 25:
                    output += f" ... ({len(rows) - 25} more rows truncated)"
                return output

        except SQLAlchemyError as err:
            # Return clear error to caller without crashing the agent
            return f"Database Query Error: {err._message() if hasattr(err, '_message') else str(err)}"
        except Exception as e:
            return f"Execution Error: {e}"


if __name__ == "__main__":
    helper = DatabaseManager()
    ok, msg = helper.test_connection()
    print(f"Connection test: {msg}")
    if ok:
        tables = ["bookings", "flights", "hotels", "customers", "cities"]
        print(helper.get_table_schema(tables, verbose=True))
        print(helper.get_table_relationships(tables, verbose=True))
        print(helper.execute_query("SELECT COUNT(*) AS total_cities FROM cities;"))