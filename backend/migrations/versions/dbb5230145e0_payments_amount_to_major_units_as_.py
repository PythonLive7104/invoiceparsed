"""payments.amount to major units as Numeric

Converts payments.amount from an integer of MINOR units (kobo/cents, how
Paystack reports money) to Numeric(18, 4) in MAJOR units (49.00 means
forty-nine).

Why: Bachs reports decimal strings in major units, so a minor-unit column
forced one provider's amounts to be converted in the wrong place. Getting that
backwards turns $49.00 into $0.49 - which is exactly what the test suite caught.
Major units are now the storage contract and each provider converts at its own
boundary.

Data impact: every existing row is divided by 100, because those values were
written in minor units.

The division is done in Python with Decimal, row by row, rather than as
`UPDATE payments SET amount = amount / 100`. That SQL looks obviously correct
and is not: SQLite has no real column types, so both operands stay integers and
4950 becomes 49 instead of 49.50 - losing the cents, silently, on exactly the
backend used for development. Postgres would have got it right, so the bug
would only have shown up locally. Decimal arithmetic in Python behaves the same
on both.

Both halves run in one migration, so a row can never be read with the new type
but the old magnitude.

The downgrade reverses it and is lossy: multiplying back by 100 and casting to
INTEGER discards any sub-minor-unit precision.

Revision ID: dbb5230145e0
Revises: 02aa3eaa91b0
Create Date: 2026-11-18 12:59:24.351260

"""
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dbb5230145e0'
down_revision = '02aa3eaa91b0'
branch_labels = None
depends_on = None


def _rescale(factor: Decimal, bind, *, divide: bool) -> None:
    """Rescale every payments.amount by `factor`, exactly, in Python.

    Reads each id/amount pair and writes the converted value back with a bound
    parameter, so the arithmetic is Decimal on every backend rather than
    whatever the database's own type coercion happens to do.
    """
    rows = bind.execute(
        sa.text("SELECT id, amount FROM payments WHERE amount IS NOT NULL")
    ).fetchall()
    for row_id, amount in rows:
        current = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        value = current / factor if divide else current * factor
        bind.execute(
            sa.text("UPDATE payments SET amount = :amount WHERE id = :id"),
            {"amount": str(value), "id": row_id},
        )


def upgrade():
    # Widen the type first so the division below is decimal, not integer.
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.INTEGER(),
               type_=sa.Numeric(precision=18, scale=4),
               existing_nullable=True)

    _rescale(Decimal(100), op.get_bind(), divide=True)


def downgrade():
    _rescale(Decimal(100), op.get_bind(), divide=False)
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.Numeric(precision=18, scale=4),
               type_=sa.INTEGER(),
               existing_nullable=True)
