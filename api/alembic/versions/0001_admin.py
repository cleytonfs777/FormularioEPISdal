"""Tabelas do fluxo de aprovação administrativa.

Revision ID: 0001_admin
Revises:
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_admin"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios_admin",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_usuarios_admin_username", "usuarios_admin", ["username"], unique=True)
    op.create_index("ix_usuarios_admin_ativo", "usuarios_admin", ["ativo"])

    op.create_table(
        "solicitacoes_alteracao",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("num_bm", sa.String(20), nullable=False),
        sa.Column("campo", sa.String(80), nullable=False),
        sa.Column("valor_anterior", sa.String(200), nullable=False, server_default=""),
        sa.Column("valor_novo", sa.String(200), nullable=False, server_default=""),
        sa.Column("solicitado_por", sa.String(80), nullable=False, server_default=""),
        sa.Column("solicitado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("decidido_por", sa.String(80), nullable=True),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_decisao", sa.String(500), nullable=True),
    )
    op.create_index("ix_solicitacoes_num_bm", "solicitacoes_alteracao", ["num_bm"])
    op.create_index("ix_solicitacoes_status", "solicitacoes_alteracao", ["status"])
    op.create_index("ix_solicitacoes_campo", "solicitacoes_alteracao", ["campo"])
    op.create_index("ix_solicitacoes_em", "solicitacoes_alteracao", ["solicitado_em"])

    op.create_table(
        "auditoria_alteracoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("num_bm", sa.String(20), nullable=False),
        sa.Column("campo", sa.String(80), nullable=False),
        sa.Column("valor_anterior", sa.String(200), nullable=False, server_default=""),
        sa.Column("valor_novo", sa.String(200), nullable=False, server_default=""),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("autor", sa.String(80), nullable=False, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auditoria_num_bm", "auditoria_alteracoes", ["num_bm"])
    op.create_index("ix_auditoria_campo", "auditoria_alteracoes", ["campo"])
    op.create_index("ix_auditoria_origem", "auditoria_alteracoes", ["origem"])
    op.create_index("ix_auditoria_ts", "auditoria_alteracoes", ["timestamp"])


def downgrade() -> None:
    op.drop_table("auditoria_alteracoes")
    op.drop_table("solicitacoes_alteracao")
    op.drop_table("usuarios_admin")
