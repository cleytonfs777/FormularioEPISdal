"""Rotas HTML do painel administrativo."""
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import API_ROOT
from ..fields_spec import EPI_ITEM_MAP
from ..lookup import buscar_militar
from ..models import AuditoriaAlteracao, SolicitacaoAlteracao, UsuarioAdmin, utcnow
from ..timeutil import agora_br, fim_dia_utc, fmt_br, inicio_dia_utc
from . import auth, service
from .deps import admin_atual, csrf_form, get_db

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(API_ROOT / "app" / "templates"))
templates.env.filters["br_dt"] = fmt_br


def _ctx(request: Request, **extra):
    data = {
        "request": request,
        "csrf_token": auth.csrf_token(request),
        "admin_user": auth.usuario_sessao(request),
        "rotulo": service.rotulo_campo,
        "now": agora_br(),
    }
    data.update(extra)
    return data


@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if auth.usuario_sessao(request):
        return RedirectResponse("/admin/pendentes", status_code=303)
    return templates.TemplateResponse("admin/login.html", _ctx(request, erro=None))


@router.post("/login")
def login_post(request: Request,
               username: str = Form(""),
               password: str = Form(""),
               csrf_token: str = Form(""),
               db: Session = Depends(get_db)):
    if not auth.csrf_ok(request, csrf_token):
        return templates.TemplateResponse(
            "admin/login.html",
            _ctx(request, erro="Sessão expirada. Tente novamente."),
            status_code=400)

    ip = auth.client_ip(request)
    if not auth.login_permitido(ip):
        return templates.TemplateResponse(
            "admin/login.html",
            _ctx(request, erro="Muitas tentativas. Aguarde alguns minutos."),
            status_code=429)

    auth.registrar_tentativa_login(ip)
    user = db.query(UsuarioAdmin).filter(UsuarioAdmin.username == username.strip()).first()
    if not user or not user.ativo or not auth.verificar_senha(password, user.password_hash):
        return templates.TemplateResponse(
            "admin/login.html",
            _ctx(request, erro="Usuário ou senha inválidos."),
            status_code=401)

    user.last_login = utcnow()
    db.commit()
    auth.gravar_sessao(request, user.username)
    return RedirectResponse("/admin/pendentes", status_code=303)


@router.post("/logout")
def logout(request: Request, _csrf: str = Depends(csrf_form)):
    auth.limpar_sessao(request)
    return RedirectResponse("/admin/login", status_code=303)


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def admin_root():
    return RedirectResponse("/admin/pendentes", status_code=303)


@router.get("/pendentes", response_class=HTMLResponse)
def pendentes(request: Request,
              num_bm: str = Query(""),
              autor: str = Query(""),
              de: str = Query(""),
              ate: str = Query(""),
              db: Session = Depends(get_db),
              admin: UsuarioAdmin = Depends(admin_atual)):
    q = db.query(SolicitacaoAlteracao).filter(SolicitacaoAlteracao.status == "pendente")
    if num_bm.strip():
        q = q.filter(SolicitacaoAlteracao.num_bm.like(f"%{num_bm.strip()}%"))
    if autor.strip():
        q = q.filter(SolicitacaoAlteracao.solicitado_por.like(f"%{autor.strip()}%"))
    if de.strip():
        q = q.filter(SolicitacaoAlteracao.solicitado_em >= inicio_dia_utc(de.strip()))
    if ate.strip():
        q = q.filter(SolicitacaoAlteracao.solicitado_em < fim_dia_utc(ate.strip()))
    rows = q.order_by(SolicitacaoAlteracao.solicitado_em.desc()).limit(500).all()
    return templates.TemplateResponse(
        "admin/pendentes.html",
        _ctx(request, rows=rows, num_bm=num_bm, autor=autor, de=de, ate=ate, admin=admin))


@router.get("/solicitacao/{sid}", response_class=HTMLResponse)
def detalhe(request: Request, sid: int,
            db: Session = Depends(get_db),
            admin: UsuarioAdmin = Depends(admin_atual)):
    sol = db.query(SolicitacaoAlteracao).filter_by(id=sid).first()
    if not sol:
        return RedirectResponse("/admin/pendentes", status_code=303)
    militar = buscar_militar(db, sol.num_bm)
    return templates.TemplateResponse(
        "admin/solicitacao_detalhe.html",
        _ctx(request, sol=sol, militar=militar, admin=admin, item_map=EPI_ITEM_MAP))


@router.post("/solicitacao/{sid}/aprovar")
def aprovar(request: Request, sid: int,
            db: Session = Depends(get_db),
            admin: UsuarioAdmin = Depends(admin_atual),
            _csrf: str = Depends(csrf_form)):
    sol = db.query(SolicitacaoAlteracao).filter_by(id=sid, status="pendente").first()
    if not sol:
        return RedirectResponse("/admin/pendentes", status_code=303)
    try:
        service.aprovar_solicitacao(db, sol, admin.username)
    except ValueError:
        return RedirectResponse(f"/admin/solicitacao/{sid}?erro=militar", status_code=303)
    return RedirectResponse("/admin/pendentes?ok=aprovada", status_code=303)


@router.post("/solicitacao/{sid}/rejeitar")
def rejeitar(request: Request, sid: int,
             motivo: str = Form(""),
             db: Session = Depends(get_db),
             admin: UsuarioAdmin = Depends(admin_atual),
             _csrf: str = Depends(csrf_form)):
    sol = db.query(SolicitacaoAlteracao).filter_by(id=sid, status="pendente").first()
    if not sol:
        return RedirectResponse("/admin/pendentes", status_code=303)
    if not motivo.strip():
        return RedirectResponse(f"/admin/solicitacao/{sid}?erro=motivo", status_code=303)
    service.rejeitar_solicitacao(db, sol, admin.username, motivo)
    return RedirectResponse("/admin/pendentes?ok=rejeitada", status_code=303)


@router.get("/historico", response_class=HTMLResponse)
def historico(request: Request,
              num_bm: str = Query(""),
              origem: str = Query(""),
              campo: str = Query(""),
              de: str = Query(""),
              ate: str = Query(""),
              db: Session = Depends(get_db),
              admin: UsuarioAdmin = Depends(admin_atual)):
    q = db.query(AuditoriaAlteracao).filter(
        AuditoriaAlteracao.origem.in_(("aprovacao", "rejeicao")))
    if num_bm.strip():
        q = q.filter(AuditoriaAlteracao.num_bm.like(f"%{num_bm.strip()}%"))
    if origem.strip():
        q = q.filter(AuditoriaAlteracao.origem == origem.strip())
    if campo.strip():
        q = q.filter(AuditoriaAlteracao.campo.like(f"%{campo.strip()}%"))
    if de.strip():
        q = q.filter(AuditoriaAlteracao.timestamp >= inicio_dia_utc(de.strip()))
    if ate.strip():
        q = q.filter(AuditoriaAlteracao.timestamp < fim_dia_utc(ate.strip()))
    rows = q.order_by(AuditoriaAlteracao.timestamp.desc()).limit(800).all()
    return templates.TemplateResponse(
        "admin/historico.html",
        _ctx(request, rows=rows, num_bm=num_bm, origem=origem, campo=campo,
             de=de, ate=ate, admin=admin))
