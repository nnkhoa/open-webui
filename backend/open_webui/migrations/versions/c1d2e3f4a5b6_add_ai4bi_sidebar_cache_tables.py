"""Add ai4bi sidebar cache tables

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-04-23 17:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai4bi_sidebar_signals',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('connection_id', sa.String(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=True),
        sa.Column('generated_at', sa.BigInteger(), nullable=False),
    )
    op.create_index(
        'ix_ai4bi_sidebar_signals_user_conn',
        'ai4bi_sidebar_signals',
        ['user_id', 'connection_id'],
    )

    op.create_table(
        'ai4bi_sidebar_heartbeat',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('connection_id', sa.String(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('delta', sa.String(), nullable=True),
        sa.Column('trend', sa.String(), nullable=False),
        sa.Column('generated_at', sa.BigInteger(), nullable=False),
    )
    op.create_index(
        'ix_ai4bi_sidebar_heartbeat_user_conn',
        'ai4bi_sidebar_heartbeat',
        ['user_id', 'connection_id'],
    )


def downgrade():
    op.drop_index('ix_ai4bi_sidebar_heartbeat_user_conn', table_name='ai4bi_sidebar_heartbeat')
    op.drop_table('ai4bi_sidebar_heartbeat')
    op.drop_index('ix_ai4bi_sidebar_signals_user_conn', table_name='ai4bi_sidebar_signals')
    op.drop_table('ai4bi_sidebar_signals')
