"""Medidas da mão (colunas L e M da Relação Nominal)."""
from alembic import op
import sqlalchemy as sa

revision = "0003_medidas_mao"
down_revision = "0002_avisos"
branch_labels = None
depends_on = None

COLUNAS = ("circunferencia_mao_cm", "comprimento_mao_cm")


def _existentes() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "militar" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("militar")}


def upgrade() -> None:
    cols = _existentes()
    if cols is None:  # banco novo: init_db() cria a tabela já com as colunas
        return
    for nome in COLUNAS:
        if nome not in cols:
            op.add_column("militar", sa.Column(nome, sa.Float(), nullable=True))


def downgrade() -> None:
    cols = _existentes() or set()
    with op.batch_alter_table("militar") as batch:
        for nome in COLUNAS:
            if nome in cols:
                batch.drop_column(nome)
