"""Dependências FastAPI do painel admin."""
from fastapi import Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..models import SessionLocal, UsuarioAdmin
from . import auth


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def admin_atual(request: Request, db: Session = Depends(get_db)) -> UsuarioAdmin:
    username = auth.usuario_sessao(request)
    if not username:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER,
                            headers={"Location": "/admin/login"})
    user = db.query(UsuarioAdmin).filter(
        UsuarioAdmin.username == username,
        UsuarioAdmin.ativo.is_(True),
    ).first()
    if not user:
        auth.limpar_sessao(request)
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER,
                            headers={"Location": "/admin/login"})
    return user


def csrf_form(request: Request, csrf_token: str = Form("")) -> str:
    if not auth.csrf_ok(request, csrf_token):
        raise HTTPException(status_code=400, detail="CSRF inválido. Recarregue a página.")
    return csrf_token
