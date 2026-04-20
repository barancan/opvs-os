"""add_tool_approvals_table

Adds the tool_approvals table which persists every tool approval request
before the agentic loop awaits user input. This ensures that:

- Approvals are visible after a process restart
- Stale PENDING approvals can be auto-expired deterministically on startup
  rather than silently lost
- The approve/reject endpoints can distinguish between "expired" and "unknown"
  request IDs, returning accurate errors to the frontend

Revision ID: a1b2c3d4e5f6
Revises: d4e1f9a2b3c5
Create Date: 2026-04-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd4e1f9a2b3c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tool_approvals',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('request_id', sa.String(64), nullable=False),
        sa.Column('tool_name', sa.String(128), nullable=False),
        sa.Column('platform', sa.String(64), nullable=False),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('parameters', sa.Text(), nullable=False, server_default='{}'),
        sa.Column(
            'status',
            sa.String(16),
            nullable=False,
            server_default='pending',
        ),
        sa.Column(
            'source',
            sa.String(16),
            nullable=False,
        ),
        sa.Column('session_uuid', sa.String(64), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tool_approvals_request_id', 'tool_approvals', ['request_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_tool_approvals_request_id', table_name='tool_approvals')
    op.drop_table('tool_approvals')
