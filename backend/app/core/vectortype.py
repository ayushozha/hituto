"""A SQLAlchemy column type that is a real pgvector ``vector`` on Postgres and JSON elsewhere.

Lets one model serve both backends: semantic search runs on Postgres (VECTOR_STORE=pgvector),
while the default SQLite dev path stores the embedding as a JSON list (and uses keyword search).
"""
from __future__ import annotations

from sqlalchemy.types import JSON, TypeDecorator


class VectorColumn(TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int, *args, **kwargs):
        self.dim = dim
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())
