"""add_event_sender_type

Adds 'event' to the SenderType enum for agent_messages.sender_type.
These rows are lightweight tool-status posts emitted after each successful
tool call in the agent loop — rendered with reduced prominence in the UI.

SQLite stores the enum as VARCHAR with no CHECK constraint, so no DDL change
is required. This migration is a schema-intent marker; it widens the column
to VARCHAR(16) on other engines that do enforce length.

Revision ID: d4e1f9a2b3c5
Revises: c03364f081a4
Create Date: 2026-04-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e1f9a2b3c5'
down_revision: Union[str, None] = 'c03364f081a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('agent_messages') as batch_op:
        batch_op.alter_column(
            'sender_type',
            existing_type=sa.String(12),
            type_=sa.String(16),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('agent_messages') as batch_op:
        batch_op.alter_column(
            'sender_type',
            existing_type=sa.String(16),
            type_=sa.String(12),
            existing_nullable=False,
        )
