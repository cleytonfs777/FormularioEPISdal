"""
Regra: só persiste o que mudou.
- Alteração comum → SQLite na hora (sem auditoria; o histórico guarda só decisões do admin).
- POSSUI → NÃO POSSUI → solicitação pendente (não grava o campo).
"""
from __future__ import annotations

import logging
import unicodedata

from sqlalchemy.orm import Session

from ..fields_spec import EPI_ITEM_MAP
from ..lookup import buscar_militar, bm_base
from ..models import (AuditoriaAlteracao, EpiItem, Militar, SolicitacaoAlteracao,
                      utcnow)
from .schemas import AlteracaoIn, AlteracaoOut, CampoAlterado

logger = logging.getLogger("epi.alteracao")

CAMPOS_GERAIS = (
    "tam_coturno", "circunferencia_mao_cm", "comprimento_mao_cm",
    "altura_cm", "peito_cm", "cintura_cm", "quadril_cm",
)
FLOAT_FIELDS = {"circunferencia_mao_cm", "comprimento_mao_cm",
                "altura_cm", "peito_cm", "cintura_cm", "quadril_cm"}


def rotulo_campo(campo: str) -> str:
    if campo.startswith("epi.") and campo.endswith(".possui"):
        key = campo.split(".")[1]
        label, _ = EPI_ITEM_MAP.get(key, (key, None))
        return f"{label} (Possui?)"
    mapa = {
        "tam_coturno": "Tam. Coturno",
        "tam_luva_salvamento": "Tam. Luva de Salvamento",
        "tam_luva_incendio": "Tam. Luva de Incêndio",
        "circunferencia_mao_cm": "Circunferência da Mão (cm)",
        "comprimento_mao_cm": "Comprimento da Mão (cm)",
        "altura_cm": "Altura (cm)",
        "peito_cm": "Peito (cm)",
        "cintura_cm": "Cintura (cm)",
        "quadril_cm": "Quadril (cm)",
    }
    if campo.startswith("epi."):
        parts = campo.split(".")
        if len(parts) == 3:
            key, attr = parts[1], parts[2]
            label, _ = EPI_ITEM_MAP.get(key, (key, None))
            nome_attr = {"cor": "Cor", "conservacao": "Conservação", "possui": "Possui?"}.get(attr, attr)
            return f"{label} — {nome_attr}"
    return mapa.get(campo, campo)


def _txt(v) -> str:
    if v is None:
        return ""
    return unicodedata.normalize("NFC", str(v).strip())


def _norm(campo: str, v) -> str:
    s = _txt(v)
    if campo in FLOAT_FIELDS and s:
        try:
            n = float(s.replace(",", "."))
            return str(int(n)) if n == int(n) else str(n)
        except ValueError:
            return s
    return s


def _valor_atual(m: Militar, campo: str) -> str:
    if campo in CAMPOS_GERAIS:
        return _norm(campo, getattr(m, campo))
    if campo.startswith("epi.") and campo.count(".") == 2:
        _, item_key, attr = campo.split(".")
        obj = next((i for i in m.itens if i.item_key == item_key), None)
        return _norm(campo, getattr(obj, attr) if obj and hasattr(obj, attr) else "")
    return ""


def _auditoria(db: Session, num_bm: str, campo: str, antes: str, depois: str,
               origem: str, autor: str, justificativa: str = "") -> None:
    db.add(AuditoriaAlteracao(
        num_bm=num_bm, campo=campo,
        valor_anterior=antes, valor_novo=depois,
        origem=origem, autor=autor,
        justificativa=justificativa,
        timestamp=utcnow(),
    ))


def _garantir_item(m: Militar, existentes: dict, item_key: str, db: Session) -> EpiItem:
    obj = existentes.get(item_key)
    if obj:
        return obj
    obj = EpiItem(militar=m, item_key=item_key)
    db.add(obj)
    existentes[item_key] = obj
    return obj


def aplicar_campo(db: Session, m: Militar, campo: str, valor_novo: str) -> None:
    """Aplica um campo já aprovado (ou direto) no militar."""
    if campo in CAMPOS_GERAIS:
        if campo in FLOAT_FIELDS:
            if valor_novo == "":
                setattr(m, campo, None)
            else:
                try:
                    setattr(m, campo, float(str(valor_novo).replace(",", ".")))
                except ValueError:
                    setattr(m, campo, None)
        else:
            setattr(m, campo, valor_novo)
        return
    if campo.startswith("epi.") and campo.count(".") == 2:
        _, item_key, attr = campo.split(".")
        existentes = {it.item_key: it for it in m.itens}
        obj = _garantir_item(m, existentes, item_key, db)
        if attr in ("possui", "cor", "conservacao"):
            setattr(obj, attr, valor_novo)
            if attr == "possui" and valor_novo != "POSSUI":
                obj.conservacao = ""


def processar_alteracao(db: Session, payload: AlteracaoIn, autor: str) -> AlteracaoOut:
    m = buscar_militar(db, payload.num_bm)
    if not m:
        raise ValueError("Militar não encontrado")

    gravados: list[str] = []
    pendentes: list[str] = []
    ids: list[int] = []
    vistos: set[str] = set()

    itens_posse_critica: set[str] = set()
    for item in payload.alteracoes:
        campo = (item.campo or "").strip()
        if not (campo.startswith("epi.") and campo.endswith(".possui")):
            continue
        key = campo.split(".")[1]
        if (_valor_atual(m, campo) == "POSSUI"
                and _norm(campo, item.valor_novo) == "NÃO POSSUI"):
            itens_posse_critica.add(key)

    for item in payload.alteracoes:
        campo = (item.campo or "").strip()
        if not campo or campo in vistos:
            continue
        if campo not in CAMPOS_GERAIS and not (
            campo.startswith("epi.") and campo.count(".") == 2
            and campo.split(".")[1] in EPI_ITEM_MAP
            and campo.split(".")[2] in ("possui", "cor", "conservacao")
        ):
            continue
        vistos.add(campo)
        if campo.startswith("epi.") and campo.count(".") == 2:
            key, attr = campo.split(".")[1], campo.split(".")[2]
            if key in itens_posse_critica and attr != "possui":
                continue
        novo = _norm(campo, item.valor_novo)
        antigo = _valor_atual(m, campo)
        if novo == antigo:
            continue

        critico = (
            campo.endswith(".possui")
            and antigo == "POSSUI"
            and novo == "NÃO POSSUI"
        )
        if critico:
            justif = (getattr(item, "justificativa", "") or "").strip()
            if not justif:
                for it in getattr(payload, "itens", []) or []:
                    it_key = it.get("item_key") if isinstance(it, dict) else getattr(it, "item_key", "")
                    if it_key == key:
                        raw_j = it.get("justificativa") if isinstance(it, dict) else getattr(it, "justificativa", "")
                        justif = str(raw_j or "").strip()
                        break

            ja = db.query(SolicitacaoAlteracao).filter_by(
                num_bm=m.num_bm, campo=campo, status="pendente").first()
            if ja:
                if justif:
                    ja.justificativa = justif
                ids.append(ja.id)
            else:
                sol = SolicitacaoAlteracao(
                    num_bm=m.num_bm,
                    campo=campo,
                    valor_anterior=antigo,
                    valor_novo=novo,
                    justificativa=justif,
                    solicitado_por=autor or payload.solicitado_por,
                    solicitado_em=utcnow(),
                    status="pendente",
                )
                db.add(sol)
                db.flush()
                ids.append(sol.id)
            pendentes.append(campo)
            continue

        aplicar_campo(db, m, campo, novo)
        gravados.append(campo)

    if not gravados and not pendentes:
        db.rollback()
        return AlteracaoOut(
            status="sem_alteracao",
            num_bm=m.num_bm,
            message="Nenhuma alteração em relação ao banco.",
        )

    if gravados:
        m.dirty = True
        m.updated_at = utcnow()
    db.commit()
    logger.info(
        "alteracao num_bm=%s gravados=%s pendentes=%s",
        m.num_bm, gravados, pendentes,
    )

    if pendentes:
        extra = ""
        if gravados:
            extra = f" {len(gravados)} campo(s) gravado(s) na hora."
        return AlteracaoOut(
            status="pendente",
            num_bm=m.num_bm,
            message="Alteração de posse (POSSUI → NÃO POSSUI) enviada para aprovação." + extra,
            ids=ids,
            gravados=gravados,
            pendentes=pendentes,
        )
    return AlteracaoOut(
        status="gravado",
        num_bm=m.num_bm,
        message=f"{len(gravados)} campo(s) gravado(s).",
        ids=[],
        gravados=gravados,
        pendentes=[],
    )


def form_completo_para_alteracoes(m: Militar, dados: dict, itens: list) -> list[CampoAlterado]:
    """Diff servidor: só os campos presentes no payload que divergem do banco."""
    out: list[CampoAlterado] = []
    for f in CAMPOS_GERAIS:
        if f not in dados:
            continue
        novo = _norm(f, dados.get(f))
        if novo != _valor_atual(m, f):
            out.append(CampoAlterado(campo=f, valor_novo=_txt(dados.get(f))))
    for item in itens or []:
        key = item.get("item_key") if isinstance(item, dict) else getattr(item, "item_key", None)
        if key not in EPI_ITEM_MAP:
            continue
        for attr in ("possui", "cor", "conservacao"):
            campo = f"epi.{key}.{attr}"
            if isinstance(item, dict):
                if attr not in item:
                    continue
                novo_raw = item.get(attr)
                justif = str(item.get("justificativa") or "").strip()
            else:
                novo_raw = getattr(item, attr)
                justif = str(getattr(item, "justificativa", "") or "").strip()
            novo = _norm(campo, novo_raw)
            if novo != _valor_atual(m, campo):
                out.append(CampoAlterado(
                    campo=campo,
                    valor_novo=_txt(novo_raw),
                    justificativa=justif if attr == "possui" else ""
                ))
    return out


def consolidar_payload(m: Militar, payload: AlteracaoIn) -> AlteracaoIn:
    """Une o diff do cliente com o diff do formulário completo vs SQLite."""
    dados = payload.model_dump()
    por_campo: dict[str, CampoAlterado] = {}
    for item in form_completo_para_alteracoes(m, dados, dados.get("itens") or []):
        por_campo[item.campo] = item
    for item in payload.alteracoes or []:
        if item.campo:
            if item.campo in por_campo and not item.justificativa:
                item.justificativa = por_campo[item.campo].justificativa
            por_campo[item.campo] = item
    return AlteracaoIn(
        num_bm=payload.num_bm,
        solicitado_por=payload.solicitado_por,
        alteracoes=list(por_campo.values()),
        itens=dados.get("itens") or [],
    )


def aprovar_solicitacao(db: Session, sol: SolicitacaoAlteracao, admin: str) -> None:
    m = buscar_militar(db, sol.num_bm)
    if not m:
        raise ValueError("Militar não encontrado para efetivar a alteração.")
    aplicar_campo(db, m, sol.campo, sol.valor_novo)
    _auditoria(db, m.num_bm, sol.campo, sol.valor_anterior, sol.valor_novo,
               "aprovacao", admin, justificativa=sol.justificativa or "")
    sol.status = "aprovada"
    sol.decidido_por = admin
    sol.decidido_em = utcnow()
    m.dirty = True
    m.updated_at = utcnow()
    criar_aviso(
        db, m.num_bm, "aprovacao",
        f"Sua solicitação de alteração em «{rotulo_campo(sol.campo)}» "
        f"({sol.valor_anterior} → {sol.valor_novo}) foi aprovada e já consta no cadastro.",
        solicitacao_id=sol.id,
    )
    db.commit()


def rejeitar_solicitacao(db: Session, sol: SolicitacaoAlteracao,
                         admin: str, motivo: str) -> None:
    motivo_limpo = motivo.strip()
    _auditoria(
        db, sol.num_bm, sol.campo,
        sol.valor_anterior,
        f"REJEITADO ({motivo_limpo})" if motivo_limpo else "REJEITADO",
        "rejeicao", admin,
        justificativa=sol.justificativa or ""
    )
    sol.status = "rejeitada"
    sol.decidido_por = admin
    sol.decidido_em = utcnow()
    sol.motivo_decisao = motivo_limpo
    criar_aviso(
        db, sol.num_bm, "rejeicao",
        f"Sua solicitação de alteração em «{rotulo_campo(sol.campo)}» "
        f"({sol.valor_anterior} → {sol.valor_novo}) foi rejeitada."
        + (f" Motivo: {motivo_limpo}" if motivo_limpo else ""),
        solicitacao_id=sol.id,
    )
    db.commit()


def criar_aviso(db: Session, num_bm: str, tipo: str, mensagem: str,
                solicitacao_id: int | None = None) -> None:
    from ..models import AvisoUsuario
    db.add(AvisoUsuario(
        num_bm=num_bm,
        tipo=tipo,
        mensagem=mensagem,
        solicitacao_id=solicitacao_id,
        criado_em=utcnow(),
    ))


def listar_avisos(db: Session, num_bm: str) -> list:
    from ..models import AvisoUsuario
    m = buscar_militar(db, num_bm)
    chave = m.num_bm if m else (num_bm or "").strip()
    base = bm_base(chave)
    if not base:
        return []
    candidatos = (
        db.query(AvisoUsuario)
        .filter(
            (AvisoUsuario.num_bm == chave)
            | (AvisoUsuario.num_bm == base)
            | (AvisoUsuario.num_bm.like(base + "-%"))
        )
        .order_by(AvisoUsuario.criado_em.asc())
        .all()
    )
    return [a for a in candidatos if bm_base(a.num_bm) == base]


def descartar_aviso(db: Session, aviso_id: int, num_bm: str) -> bool:
    from ..models import AvisoUsuario
    av = db.query(AvisoUsuario).filter_by(id=aviso_id).first()
    if not av:
        return False
    m = buscar_militar(db, num_bm)
    chave = m.num_bm if m else num_bm
    if bm_base(av.num_bm) != bm_base(chave) and av.num_bm != chave:
        return False
    db.delete(av)
    db.commit()
    return True
