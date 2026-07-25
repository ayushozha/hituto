"""pgvector embedding column + HNSW index (Postgres only)

Converts source_chunks.embedding (JSON in the initial migration) to a real pgvector
``vector`` and adds a cosine HNSW index. The dimension is taken from the app config
(``EMBEDDING_DIM``) so it always matches the ORM column + the embedding model — hardcoding it
caused a size mismatch (config default 1536 vs a 4096-dim model). Postgres-only: on any other
dialect this is a no-op (SQLite dev stores embeddings as JSON via create_all + keyword search).

Revision ID: a1b2c3d4e5f6
Revises: ff9f097796bf
"""
from alembic import op

from app.core.config import get_settings

revision = "a1b2c3d4e5f6"
down_revision = "ff9f097796bf"
branch_labels = None
depends_on = None

# pgvector's HNSW/IVFFlat indexes support at most 2000 dimensions.
_HNSW_MAX_DIM = 2000


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    dim = get_settings().embedding_dim
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Table is freshly migrated and empty, so a drop+add is the clean way to switch types.
    op.execute("ALTER TABLE source_chunks DROP COLUMN IF EXISTS embedding")
    op.execute(f"ALTER TABLE source_chunks ADD COLUMN embedding vector({dim})")
    # Skip the ANN index above the HNSW dimension cap — per-document retrieval scans a small,
    # source-scoped candidate set, so a sequential cosine scan is fine at high dimensions.
    if dim <= _HNSW_MAX_DIM:
        op.execute(
            "CREATE INDEX IF NOT EXISTS source_chunks_embedding_hnsw "
            "ON source_chunks USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS source_chunks_embedding_hnsw")
    op.execute("ALTER TABLE source_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE source_chunks ADD COLUMN embedding jsonb")
