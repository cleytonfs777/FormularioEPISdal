"""Avisos descartáveis ao usuário (aprovação / rejeição)."""
from alembic import op
import sqlalchemy as sa

revision = "0002_avisos"
down_revision = "0001_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "avisos_usuario",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("num_bm", sa.String(20), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("mensagem", sa.String(800), nullable=False, server_default=""),
        sa.Column("solicitacao_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_avisos_usuario_num_bm", "avisos_usuario", ["num_bm"])
    op.create_index("ix_avisos_usuario_tipo", "avisos_usuario", ["tipo"])
    op.create_index("ix_avisos_usuario_criado_em", "avisos_usuario", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_avisos_usuario_criado_em", table_name="avisos_usuario")
    op.drop_index("ix_avisos_usuario_tipo", table_name="avisos_usuario")
    op.drop_index("ix_avisos_usuario_num_bm", table_name="avisos_usuario")
    op.drop_table("avisos_usuario")
