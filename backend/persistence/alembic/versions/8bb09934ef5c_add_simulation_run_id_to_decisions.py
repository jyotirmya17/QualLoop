"""add_simulation_run_id_to_decisions

Revision ID: 8bb09934ef5c
Revises: 7aa98823fe4b
Create Date: 2026-10-25 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bb09934ef5c'
down_revision: Union[str, Sequence[str], None] = '7aa98823fe4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add simulation_run_id column, index, and unique constraint to decisions."""
    with op.batch_alter_table('decisions') as batch_op:
        batch_op.add_column(sa.Column('simulation_run_id', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_decisions_simulation_run_id'), ['simulation_run_id'], unique=False)
        batch_op.create_unique_constraint('uq_decisions_run_ad_policy', ['simulation_run_id', 'advertisement_id', 'policy_version'])


def downgrade() -> None:
    """Revert simulation_run_id column, index, and unique constraint."""
    with op.batch_alter_table('decisions') as batch_op:
        batch_op.drop_constraint('uq_decisions_run_ad_policy', type_='unique')
        batch_op.drop_index(batch_op.f('ix_decisions_simulation_run_id'))
        batch_op.drop_column('simulation_run_id')
