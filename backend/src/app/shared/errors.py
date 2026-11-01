"""Structured database initialization failures."""


class MissingDatabaseSchemaError(RuntimeError):
    def __init__(self, *, table: str) -> None:
        super().__init__("Database schema is missing; run Alembic upgrade head first")
        self.table = table
