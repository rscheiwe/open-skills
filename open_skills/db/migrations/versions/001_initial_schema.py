"""Initial schema with pgvector support

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create orgs table
    op.create_table(
        'orgs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )

    # Create skills table
    op.create_table(
        'skills',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('visibility', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("visibility IN ('user', 'org')", name='check_skill_visibility'),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_skills_org_id', 'skills', ['org_id'])
    op.create_index('idx_skills_owner_id', 'skills', ['owner_id'])

    # Create skill_versions table
    op.create_table(
        'skill_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('skill_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('entrypoint', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('metadata_yaml', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('bundle_path', sa.Text(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_skill_versions_published', 'skill_versions', ['is_published'])
    op.create_index('idx_skill_versions_skill_id', 'skill_versions', ['skill_id'])
    op.create_index(
        'idx_skill_versions_unique',
        'skill_versions',
        ['skill_id', 'version'],
        unique=True,
    )
    # Create pgvector index for embeddings
    op.execute(
        'CREATE INDEX idx_skill_versions_embedding ON skill_versions '
        'USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)'
    )

    # Create skill_runs table
    op.create_table(
        'skill_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('skill_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('input_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('artifact_url', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('logs', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'error', 'cancelled')",
            name='check_run_status',
        ),
        sa.ForeignKeyConstraint(['skill_version_id'], ['skill_versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_skill_runs_created_at', 'skill_runs', ['created_at'])
    op.create_index('idx_skill_runs_skill_version_id', 'skill_runs', ['skill_version_id'])
    op.create_index('idx_skill_runs_status', 'skill_runs', ['status'])
    op.create_index('idx_skill_runs_user_id', 'skill_runs', ['user_id'])

    # Create skill_artifacts table
    op.create_table(
        'skill_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('s3_url', sa.Text(), nullable=True),
        sa.Column('local_path', sa.Text(), nullable=True),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('mime_type', sa.String(length=255), nullable=True),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['skill_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_skill_artifacts_run_id', 'skill_artifacts', ['run_id'])

    # Create skill_permissions table
    op.create_table(
        'skill_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('skill_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('viewer', 'author', 'publisher', 'admin')",
            name='check_permission_role',
        ),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_skill_permissions_org_id', 'skill_permissions', ['org_id'])
    op.create_index('idx_skill_permissions_skill_id', 'skill_permissions', ['skill_id'])
    op.create_index('idx_skill_permissions_user_id', 'skill_permissions', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_skill_permissions_user_id', table_name='skill_permissions')
    op.drop_index('idx_skill_permissions_skill_id', table_name='skill_permissions')
    op.drop_index('idx_skill_permissions_org_id', table_name='skill_permissions')
    op.drop_table('skill_permissions')

    op.drop_index('idx_skill_artifacts_run_id', table_name='skill_artifacts')
    op.drop_table('skill_artifacts')

    op.drop_index('idx_skill_runs_user_id', table_name='skill_runs')
    op.drop_index('idx_skill_runs_status', table_name='skill_runs')
    op.drop_index('idx_skill_runs_skill_version_id', table_name='skill_runs')
    op.drop_index('idx_skill_runs_created_at', table_name='skill_runs')
    op.drop_table('skill_runs')

    op.execute('DROP INDEX IF EXISTS idx_skill_versions_embedding')
    op.drop_index('idx_skill_versions_unique', table_name='skill_versions')
    op.drop_index('idx_skill_versions_skill_id', table_name='skill_versions')
    op.drop_index('idx_skill_versions_published', table_name='skill_versions')
    op.drop_table('skill_versions')

    op.drop_index('idx_skills_owner_id', table_name='skills')
    op.drop_index('idx_skills_org_id', table_name='skills')
    op.drop_table('skills')

    op.drop_table('users')
    op.drop_table('orgs')

    op.execute('DROP EXTENSION IF EXISTS vector')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
