from datetime import datetime, timezone

from sqlalchemy import (String, Integer, Float, Boolean, DateTime,
                        ForeignKey, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
_engine_kwargs: dict = (
    {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if _is_sqlite else {"pool_pre_ping": True}
)
engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _connection_record):
        cur = dbapi_conn.cursor()
        cur.execute(f"PRAGMA journal_mode={settings.sqlite_journal_mode}")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Militar(Base):
    """
    Cabeçalho (dados não-editáveis no form) + dados gerais editáveis.
    Chave de negócio: num_bm.
    """
    __tablename__ = "militar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    num_bm: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # Não-editáveis (preenchidos a partir da base)
    posto_grad: Mapped[str] = mapped_column(String(40), default="")
    descricao_quadro: Mapped[str] = mapped_column(String(120), default="")
    nome_completo: Mapped[str] = mapped_column(String(160), default="")
    ativo_inativo: Mapped[str] = mapped_column(String(20), default="")
    situacao_funcional: Mapped[str] = mapped_column(String(120), default="")
    unidade_principal: Mapped[str] = mapped_column(String(120), default="")
    unidade_lotacao: Mapped[str] = mapped_column(String(120), default="")

    # Dados gerais (editáveis)
    tam_coturno: Mapped[str] = mapped_column(String(20), default="")
    tam_luva_salvamento: Mapped[str] = mapped_column(String(80), default="")
    tam_luva_incendio: Mapped[str] = mapped_column(String(80), default="")
    circunferencia_mao_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    comprimento_mao_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    altura_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    peito_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    cintura_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    quadril_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Termo de veracidade: controla se o popup já foi aceito
    termo_aceito: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    termo_aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                            nullable=True)

    # Controle de sync
    dirty: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, onupdate=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                       nullable=True)

    itens: Mapped[list["EpiItem"]] = relationship(
        back_populates="militar", cascade="all, delete-orphan", lazy="selectin")


class EpiItem(Base):
    """
    Tabela filha: um registro por item de EPI do militar.
    item_key identifica o item (ex.: 'multimissao_bota').
    """
    __tablename__ = "militar_epi_item"
    __table_args__ = (UniqueConstraint("militar_id", "item_key",
                                       name="uq_militar_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    militar_id: Mapped[int] = mapped_column(ForeignKey("militar.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(50), index=True)

    possui: Mapped[str] = mapped_column(String(15), default="")        # POSSUI / NÃO POSSUI
    cor: Mapped[str] = mapped_column(String(15), default="")           # quando aplicável
    conservacao: Mapped[str] = mapped_column(String(15), default="")   # ÓTIMO/BOM/...

    militar: Mapped["Militar"] = relationship(back_populates="itens")


class UsuarioAdmin(Base):
    """Operador do painel de aprovação."""
    __tablename__ = "usuarios_admin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SolicitacaoAlteracao(Base):
    """Pedido de alteração crítica (POSSUI → NÃO POSSUI) aguardando admin."""
    __tablename__ = "solicitacoes_alteracao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    num_bm: Mapped[str] = mapped_column(String(20), index=True)
    campo: Mapped[str] = mapped_column(String(80), index=True)
    valor_anterior: Mapped[str] = mapped_column(String(200), default="")
    valor_novo: Mapped[str] = mapped_column(String(200), default="")
    justificativa: Mapped[str] = mapped_column(String(500), default="")
    solicitado_por: Mapped[str] = mapped_column(String(80), default="")
    solicitado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                    default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pendente", index=True)
    decidido_por: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         nullable=True)
    motivo_decisao: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AuditoriaAlteracao(Base):
    """Trilha de alterações e decisões do admin (inclui rejeições)."""
    __tablename__ = "auditoria_alteracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    num_bm: Mapped[str] = mapped_column(String(20), index=True)
    campo: Mapped[str] = mapped_column(String(80), index=True)
    valor_anterior: Mapped[str] = mapped_column(String(200), default="")
    valor_novo: Mapped[str] = mapped_column(String(200), default="")
    origem: Mapped[str] = mapped_column(String(20), index=True)  # aprovacao | rejeicao (direta: só registros antigos)
    autor: Mapped[str] = mapped_column(String(80), default="")
    justificativa: Mapped[str] = mapped_column(String(500), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                default=utcnow, index=True)


class AvisoUsuario(Base):
    """Aviso descartável para o militar (aprovação/rejeição). Apagado ao confirmar leitura."""
    __tablename__ = "avisos_usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    num_bm: Mapped[str] = mapped_column(String(20), index=True)
    tipo: Mapped[str] = mapped_column(String(20), index=True)  # aprovacao | rejeicao
    mensagem: Mapped[str] = mapped_column(String(800), default="")
    solicitacao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                default=utcnow, index=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
    if _is_sqlite:
        with engine.begin() as conn:
            cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(militar)")}
            if "termo_aceito" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE militar ADD COLUMN termo_aceito BOOLEAN NOT NULL DEFAULT 0")
            if "termo_aceito_em" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE militar ADD COLUMN termo_aceito_em DATETIME")
            for col in ("circunferencia_mao_cm", "comprimento_mao_cm"):
                if col not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE militar ADD COLUMN {col} REAL")
            cols_sol = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(solicitacoes_alteracao)")}
            if "justificativa" not in cols_sol:
                conn.exec_driver_sql(
                    "ALTER TABLE solicitacoes_alteracao ADD COLUMN justificativa VARCHAR(500) DEFAULT ''")
            cols_aud = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(auditoria_alteracoes)")}
            if "justificativa" not in cols_aud:
                conn.exec_driver_sql(
                    "ALTER TABLE auditoria_alteracoes ADD COLUMN justificativa VARCHAR(500) DEFAULT ''")
