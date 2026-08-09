"""
SQLAlchemy Base + a cross-dialect GUID column type.

Production runs on PostgreSQL (native UUID + gen_random_uuid()); unit/integration
tests run against in-memory SQLite for speed and zero external dependencies. Postgres'
native UUID type isn't available on SQLite, so GUID stores as CHAR(36) there while
still round-tripping as `uuid.UUID` in Python on both backends — this is what makes
the same repository code and the same test suite work on both engines (NFR-PORT-1).
"""
from __future__ import annotations

import uuid

from sqlalchemy import CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class Base(DeclarativeBase):
    pass
