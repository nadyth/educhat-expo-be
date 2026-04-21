"""rename page_index to page_label

Revision ID: 3cdc15496fe3
Revises: 3499540d54d5
Create Date: 2026-04-20 04:09:39.211105

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cdc15496fe3'
down_revision: Union[str, Sequence[str], None] = '3499540d54d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename page_index to page_label and change type from integer to string."""
    # Rename column
    op.alter_column('document_contents', 'page_index', new_column_name='page_label')
    # Change type from integer to varchar(32), using page_number as backfill value
    op.execute(
        "ALTER TABLE document_contents "
        "ALTER COLUMN page_label TYPE VARCHAR(32) USING page_number::text"
    )


def downgrade() -> None:
    """Rename page_label back to page_index and change type back to integer."""
    op.execute(
        "ALTER TABLE document_contents "
        "ALTER COLUMN page_label TYPE INTEGER USING page_label::integer"
    )
    op.alter_column('document_contents', 'page_label', new_column_name='page_index')