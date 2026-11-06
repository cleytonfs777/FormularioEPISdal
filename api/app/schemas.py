from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from .fields_spec import (DADOS_GERAIS, EPI_ITEM_MAP, MILITAR_READONLY,
                          POSTO_GRAD, COTURNO, LUVA, POSSUI, CONSERVACAO,
                          COR_CAPACETE, COR_CONJ_CIURB)

# Campos editáveis "Dados gerais" obrigatórios (Not Null na spec)
DADOS_GERAIS_REQUIRED = [
    "tam_coturno", "circunferencia_mao_cm", "comprimento_mao_cm",
    "altura_cm", "peito_cm", "cintura_cm", "quadril_cm",
]
DADOS_GERAIS_LABELS = {k: label for k, label, *_ in DADOS_GERAIS}


class EpiItemIn(BaseModel):
    item_key: str
    possui: str = ""
    cor: str = ""
    conservacao: str = ""
    justificativa: str = ""


class EpiItemOut(EpiItemIn):
    model_config = ConfigDict(from_attributes=True)


class MilitarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    num_bm: str
    posto_grad: str = ""
    descricao_quadro: str = ""
    descricao: str = ""
    nome_completo: str = ""
    ativo_inativo: str = ""
    situacao_funcional: str = ""
    unidade_principal: str = ""
    unidade_lotacao: str = ""
    tam_coturno: str = ""
    circunferencia_mao_cm: float | None = None
    comprimento_mao_cm: float | None = None
    altura_cm: float | None = None
    peito_cm: float | None = None
    cintura_cm: float | None = None
    quadril_cm: float | None = None
    termo_aceito: bool = False
    termo_aceito_em: datetime | None = None
    itens: list[EpiItemOut] = []

    @model_validator(mode="after")
    def fill_descricao(self):
        if not self.descricao:
            self.descricao = self.descricao_quadro or ""
        return self


class ConsultaOut(MilitarRead):
    """Resposta da extensão: inclui alias 'descricao' = descricao_quadro."""
    pass


class MilitarUpdate(BaseModel):
    """Payload de envio do formulário (somente campos editáveis)."""
    tam_coturno: str = ""
    circunferencia_mao_cm: float | None = None
    comprimento_mao_cm: float | None = None
    altura_cm: float | None = None
    peito_cm: float | None = None
    cintura_cm: float | None = None
    quadril_cm: float | None = None
    itens: list[EpiItemIn] = []

    def missing_required(self) -> list[str]:
        faltando = []
        for field in DADOS_GERAIS_REQUIRED:
            value = getattr(self, field, None)
            if value is None or str(value).strip() == "":
                faltando.append(DADOS_GERAIS_LABELS.get(field, field))
        # Regra: cada item marcado POSSUI exige estado de conservação
        for item in self.itens:
            if item.possui == "POSSUI" and not item.conservacao.strip():
                label, _ = EPI_ITEM_MAP.get(item.item_key, (item.item_key, None))
                faltando.append(f"Conservação de '{label}'")
        return faltando


class FormSpec(BaseModel):
    """Especificação enviada ao front para montar o formulário."""
    militar_readonly: list = MILITAR_READONLY
    dados_gerais: list = DADOS_GERAIS
    options: dict = {
        "posto_grad": POSTO_GRAD, "coturno": COTURNO, "luva": LUVA,
        "possui": POSSUI, "conservacao": CONSERVACAO,
        "cor_capacete": COR_CAPACETE, "cor_conj_ciurb": COR_CONJ_CIURB,
    }
