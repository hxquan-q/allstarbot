"""070_schema_embedding_vector

Add pgvector ``embedding_vector`` columns to ``core_table`` / ``core_datasource``
/ ``core_field`` for the new RAG retrieval layer (``apps.datasource.retrieval``),
plus HNSW cosine indexes. The legacy JSON-text ``embedding`` columns are kept
intact for back-compat during the migration window (the numpy-based ranking in
``apps/datasource/embedding/`` still reads them until Phase 2 rewires retrieval
to pgvector).

Best-effort backfill: the legacy ``embedding`` column stores a JSON array
(``"[0.1, 0.2, ...]"``), which is text-compatible with pgvector's literal
format, so we cast and only fill NULLs (re-run safe). ``core_field`` has no
legacy embedding column — field embeddings are generated separately
(column-level retrieval dependency, future).

NOTE: written + reviewed, not executed in the Phase 1 sandbox (no live
Postgres + pgvector binding there). Run on a real instance with the ``vector``
extension available.

Revision ID: 0a1b2c3d4e5f
Revises: 1f82cad3546e
Create Date: 2026-06-23
"""
from alembic import op
import pgvector
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0a1b2c3d4e5f'
down_revision = '1f82cad3546e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.add_column('core_table', sa.Column('embedding_vector', pgvector.sqlalchemy.vector.VECTOR(), nullable=True))
    op.add_column('core_datasource', sa.Column('embedding_vector', pgvector.sqlalchemy.vector.VECTOR(), nullable=True))
    op.add_column('core_field', sa.Column('embedding_vector', pgvector.sqlalchemy.vector.VECTOR(), nullable=True))

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_core_table_embedding_vector "
        "ON core_table USING hnsw (embedding_vector vector_cosine_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_core_datasource_embedding_vector "
        "ON core_datasource USING hnsw (embedding_vector vector_cosine_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_core_field_embedding_vector "
        "ON core_field USING hnsw (embedding_vector vector_cosine_ops);"
    )

    # Best-effort backfill from legacy JSON-text embedding (re-run safe).
    op.execute(
        "UPDATE core_table SET embedding_vector = embedding::vector "
        "WHERE embedding_vector IS NULL AND embedding IS NOT NULL AND embedding LIKE '[%';"
    )
    op.execute(
        "UPDATE core_datasource SET embedding_vector = embedding::vector "
        "WHERE embedding_vector IS NULL AND embedding IS NOT NULL AND embedding LIKE '[%';"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_core_field_embedding_vector;")
    op.execute("DROP INDEX IF EXISTS ix_core_datasource_embedding_vector;")
    op.execute("DROP INDEX IF EXISTS ix_core_table_embedding_vector;")
    op.drop_column('core_field', 'embedding_vector')
    op.drop_column('core_datasource', 'embedding_vector')
    op.drop_column('core_table', 'embedding_vector')
