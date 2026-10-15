"""Add the replacement pipeline revision ledger and consumer views.

Revision ID: 20261015_0003
Revises: 20260920_0002
"""
from alembic import op

revision = "20261015_0003"
down_revision = "20260920_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE pipeline_target (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            environment text NOT NULL CHECK (environment IN ('dev','nonprod','prod')),
            target_id uuid NOT NULL UNIQUE,
            token_secret text NOT NULL
        );
        CREATE TABLE pipeline_records (
            sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
            dataset text NOT NULL,
            record_key text NOT NULL,
            revision bigint NOT NULL CHECK (revision > 0),
            accepted_at timestamptz NOT NULL,
            run_id uuid NOT NULL,
            envelope jsonb NOT NULL,
            payload jsonb NOT NULL,
            PRIMARY KEY (dataset, record_key, revision)
        );
        CREATE INDEX pipeline_records_snapshot_idx
            ON pipeline_records (dataset, record_key, sequence DESC);
        CREATE TABLE pipeline_receipts (
            batch_id uuid PRIMARY KEY,
            receipt jsonb NOT NULL
        );
        CREATE VIEW pipeline_current AS
            SELECT DISTINCT ON (dataset, record_key) * FROM pipeline_records
            ORDER BY dataset, record_key, revision DESC;
    """)
    # Keep this migration self-contained; later view changes use new revisions.
    from pathlib import Path
    import hashlib
    path = Path(__file__).with_name("pipeline_views_v1.sql")
    sql = path.read_text()
    if hashlib.sha256(sql.encode()).hexdigest() != VIEWS_SHA256:
        raise RuntimeError("Frozen pipeline view definitions changed")
    op.execute(sql)


def downgrade():
    op.execute("""
        DROP SCHEMA pipeline_api CASCADE;
        DROP VIEW pipeline_current;
        DROP TABLE pipeline_receipts;
        DROP TABLE pipeline_records;
        DROP TABLE pipeline_target;
    """)


VIEWS_SHA256 = '9364164fa7f4c27c451567d8c3201db233c976a21169763019cbc7cf864c2ef0'
