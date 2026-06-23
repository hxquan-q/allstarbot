"""pgvector-backed similarity search for schema retrieval.

Builds parameterised cosine-distance (``<=>``) SQL for table / datasource /
column vector search, mirroring the proven pattern in
``apps/terminology/curd/terminology.py``. pgvector is imported lazily — only
the execution layer needs it to bind the vector parameter — so this module
imports and is unit-testable with pgvector NOT installed.

Table/column names match the ``CoreTable`` / ``CoreDatasource`` / ``CoreField``
models (``apps/datasource/models/datasource.py``):

* ``core_datasource``: id, name, oid, embedding(Text)
* ``core_table``:      id, ds_id, table_name, table_comment, embedding(Text)
* ``core_field``:      id, ds_id, table_id, field_name, field_comment  (no embedding yet)

The vector column ``embedding_vector`` is added by the companion alembic
migration; the legacy JSON-text ``embedding`` column is left intact for
back-compat during the migration window. Column-level search additionally
requires ``core_field.embedding_vector`` to be populated (future: field
embedding generation), so it is provided but not yet wired.
"""
from __future__ import annotations

from typing import Optional

_VECTOR_COLUMN = "embedding_vector"


class PgvectorSchemaStore:
    """Builds pgvector similarity-search SQL (template + params).

    The returned ``sql`` uses a ``:embedding`` named placeholder; the caller
    binds ``params["embedding"]`` via the pgvector SQLAlchemy adapter at
    execution time (Phase 2 wiring).
    """

    def __init__(self, dim: int):
        self.dim = dim

    def search_tables_sql(
        self,
        embedding,
        *,
        ds_id: Optional[int] = None,
        min_similarity: float = 0.3,
        top_k: int = 10,
    ):
        clauses = []
        params: dict = {"embedding": embedding}
        if ds_id is not None:
            clauses.append("ds_id = :ds_id")
            params["ds_id"] = ds_id
        where = ("AND " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
SELECT id, ds_id, table_name, table_comment, similarity
FROM (
  SELECT id, ds_id, table_name, table_comment,
         (1 - ({_VECTOR_COLUMN} <=> :embedding)) AS similarity
  FROM core_table
  WHERE 1=1 {where}
) t
WHERE similarity > {float(min_similarity)}
ORDER BY similarity DESC
LIMIT {int(top_k)}
"""
        return sql, params

    def search_datasources_sql(
        self,
        embedding,
        *,
        oid: Optional[int] = None,
        min_similarity: float = 0.3,
        top_k: int = 10,
    ):
        clauses = []
        params: dict = {"embedding": embedding}
        if oid is not None:
            clauses.append("oid = :oid")
            params["oid"] = oid
        where = ("AND " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
SELECT id, name, similarity
FROM (
  SELECT id, oid, name,
         (1 - ({_VECTOR_COLUMN} <=> :embedding)) AS similarity
  FROM core_datasource
  WHERE 1=1 {where}
) t
WHERE similarity > {float(min_similarity)}
ORDER BY similarity DESC
LIMIT {int(top_k)}
"""
        return sql, params

    def search_columns_sql(
        self,
        embedding,
        *,
        table_id: Optional[int] = None,
        ds_id: Optional[int] = None,
        min_similarity: float = 0.3,
        top_k: int = 20,
    ):
        clauses = []
        params: dict = {"embedding": embedding}
        if table_id is not None:
            clauses.append("table_id = :table_id")
            params["table_id"] = table_id
        if ds_id is not None:
            clauses.append("ds_id = :ds_id")
            params["ds_id"] = ds_id
        where = ("AND " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
SELECT id, table_id, field_name, field_comment, similarity
FROM (
  SELECT id, table_id, ds_id, field_name, field_comment,
         (1 - ({_VECTOR_COLUMN} <=> :embedding)) AS similarity
  FROM core_field
  WHERE 1=1 {where}
) t
WHERE similarity > {float(min_similarity)}
ORDER BY similarity DESC
LIMIT {int(top_k)}
"""
        return sql, params
