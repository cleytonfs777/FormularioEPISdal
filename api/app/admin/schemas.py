"""Schemas do fluxo de alterações (extensão → API)."""
from pydantic import BaseModel, ConfigDict, Field


class CampoAlterado(BaseModel):
    """Um único campo que o militar de fato mudou no formulário."""
    campo: str = Field(..., min_length=1)
    valor_novo: str = ""
    justificativa: str = ""


class AlteracaoIn(BaseModel):
    """Diff opcional + formulário completo (extras permitidos para o servidor calcular o que mudou)."""
    model_config = ConfigDict(extra="allow")

    num_bm: str = Field(..., min_length=1)
    solicitado_por: str = ""
    alteracoes: list[CampoAlterado] = []
    itens: list[dict] = []


class AlteracaoOut(BaseModel):
    status: str  # gravado | pendente | sem_alteracao
    num_bm: str
    message: str
    ids: list[int] = []
    gravados: list[str] = []
    pendentes: list[str] = []
