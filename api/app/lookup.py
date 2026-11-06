"""Busca de militar por Nº BM (com ou sem dígito verificador) ou nome."""
from sqlalchemy.orm import Session

from .models import Militar


def bm_base(num_bm: str) -> str:
    """142924-0 → 142924 (remove traço e dígito verificador)."""
    s = (num_bm or "").replace("\xa0", "").replace(" ", "").strip()
    if "-" in s:
        s = s.split("-", 1)[0]
    return s


def buscar_militar(db: Session, q: str) -> Militar | None:
    q = bm_base(q)
    if not q:
        return None
    m = db.query(Militar).filter(Militar.num_bm == q).first()
    if m:
        return m
    candidatos = db.query(Militar).filter(Militar.num_bm.like(q + "-%")).all()
    for row in candidatos:
        if bm_base(row.num_bm) == q:
            return row
    if not q.isdigit():
        return db.query(Militar).filter(Militar.nome_completo.ilike(f"%{q}%")).first()
    return None
