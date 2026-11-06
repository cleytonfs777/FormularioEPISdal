import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from .admin.auth import fingerprint_autor, usuario_sessao
from .admin.routes import router as admin_router
from .admin.schemas import AlteracaoIn, AlteracaoOut
from .admin.service import (
    consolidar_payload, descartar_aviso, form_completo_para_alteracoes,
    listar_avisos, processar_alteracao,
)
from .config import API_ROOT, settings
from .lookup import buscar_militar
from .models import Militar, SessionLocal, SolicitacaoAlteracao, init_db, utcnow
from .schemas import ConsultaOut, FormSpec, MilitarRead, MilitarUpdate
from .sheets_sync import get_last_sync, sync_now
from .timeutil import agora_br, iso_br

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("epi.api")

class ProtegerAdminMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        livre = path == "/admin/login" or path.startswith("/static/")
        if path.startswith("/admin") and not livre and not usuario_sessao(request):
            return RedirectResponse("/admin/login", status_code=303)
        return await call_next(request)


app = FastAPI(title="CBMMG - API Controle de EPIs", version="2.2.0")

app.add_middleware(ProtegerAdminMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.allowed_origins == "*" else [settings.allowed_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)
_cookie_https = bool(os.getenv("RAILWAY_ENVIRONMENT")) or os.getenv(
    "SESSION_HTTPS_ONLY", "").strip().lower() in {"1", "true", "yes"}
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="epi_admin_session",
    same_site="lax",
    https_only=_cookie_https,
    max_age=60 * 60 * 8,
)

STATIC_DIR = API_ROOT / "app" / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(admin_router)

try:
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
except Exception:
    scheduler = BackgroundScheduler()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_secret(x_secret_code: str = Header(default="")):
    if x_secret_code != settings.secret_code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="secret_code inválido")


def _to_consulta(m: Militar) -> ConsultaOut:
    data = MilitarRead.model_validate(m).model_dump()
    data["descricao"] = data.get("descricao_quadro") or ""
    return ConsultaOut(**data)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("DB: %s", settings.database_url)
    logger.info("Credenciais: %s", settings.google_credentials_file)
    logger.info("Planilha: %s / aba '%s'", settings.spreadsheet_id, settings.sheet_name)

    scheduler.add_job(
        sync_now,
        "interval",
        seconds=settings.sync_interval_seconds,
        id="sheets_sync",
        max_instances=1,
        coalesce=True,
        next_run_time=agora_br(),
    )
    scheduler.start()
    logger.info("Scheduler: sync DB↔planilha imediato + a cada %ss",
                settings.sync_interval_seconds)


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown(wait=False)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    total = db.query(func.count(Militar.id)).scalar() or 0
    dirty = db.query(func.count(Militar.id)).filter(Militar.dirty.is_(True)).scalar() or 0
    return {
        "status": "ok",
        "database": settings.database_url.split("://")[0],
        "database_url": settings.database_url,
        "militares": total,
        "pending_dirty": dirty,
        "sync_interval_seconds": settings.sync_interval_seconds,
        "last_sync": get_last_sync(),
    }


@app.get("/form-spec", response_model=FormSpec, dependencies=[Depends(require_secret)])
def form_spec():
    return FormSpec()


@app.get("/consulta", response_model=ConsultaOut)
def consulta_militar(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    m = buscar_militar(db, q)
    if not m:
        raise HTTPException(status_code=404, detail="Militar não encontrado")
    return _to_consulta(m)


@app.post("/consulta/termo")
def aceitar_termo(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    m = buscar_militar(db, q)
    if not m:
        raise HTTPException(status_code=404, detail="Militar não encontrado")
    m.termo_aceito = True
    m.termo_aceito_em = utcnow()
    db.commit()
    return {"status": "ok", "num_bm": m.num_bm, "termo_aceito": True,
            "termo_aceito_em": iso_br(m.termo_aceito_em)}


@app.get("/consulta/avisos")
def consulta_avisos(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    """Avisos pendentes de leitura (aprovação/rejeição). Descartados após confirmação."""
    avisos = listar_avisos(db, q)
    sol_ids = {a.solicitacao_id for a in avisos if a.solicitacao_id}
    campos = dict(
        db.query(SolicitacaoAlteracao.id, SolicitacaoAlteracao.campo)
        .filter(SolicitacaoAlteracao.id.in_(sol_ids)).all()
    ) if sol_ids else {}
    return {
        "num_bm": q,
        "avisos": [
            {
                "id": a.id,
                "tipo": a.tipo,
                "mensagem": a.mensagem,
                "campo": campos.get(a.solicitacao_id, ""),
                "criado_em": iso_br(a.criado_em),
            }
            for a in avisos
        ],
    }


@app.post("/consulta/avisos/{aviso_id}/lida")
def consulta_aviso_lida(aviso_id: int, q: str = Query(..., min_length=1),
                        db: Session = Depends(get_db)):
    if not descartar_aviso(db, aviso_id, q):
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    return {"status": "ok", "id": aviso_id}


@app.post("/api/alteracoes", response_model=AlteracaoOut)
def api_alteracoes(payload: AlteracaoIn, request: Request, db: Session = Depends(get_db)):
    """Compara o formulário com o SQLite e grava só o que mudou."""
    m = buscar_militar(db, payload.num_bm)
    if not m:
        raise HTTPException(status_code=404, detail="Militar não encontrado")
    body = consolidar_payload(m, payload)
    if not body.alteracoes:
        return AlteracaoOut(
            status="sem_alteracao",
            num_bm=m.num_bm,
            message="Nenhuma alteração em relação ao banco.",
        )
    autor = payload.solicitado_por or fingerprint_autor(request, payload.num_bm)
    try:
        return processar_alteracao(db, body, autor)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/militar/{num_bm}", response_model=ConsultaOut,
         dependencies=[Depends(require_secret)])
def get_militar(num_bm: str, db: Session = Depends(get_db)):
    m = buscar_militar(db, num_bm)
    if not m:
        raise HTTPException(status_code=404, detail="Militar não encontrado")
    return _to_consulta(m)


@app.put("/militar/{num_bm}", response_model=AlteracaoOut,
         dependencies=[Depends(require_secret)])
def update_militar(num_bm: str, payload: MilitarUpdate, request: Request,
                   db: Session = Depends(get_db)):
    """PUT legado: calcula o diff no servidor e segue a mesma regra."""
    m = buscar_militar(db, num_bm)
    if not m:
        raise HTTPException(status_code=404, detail="Militar não encontrado")
    diffs = form_completo_para_alteracoes(m, payload.model_dump(exclude_unset=True), payload.itens)
    body = AlteracaoIn(num_bm=num_bm, alteracoes=diffs)
    autor = fingerprint_autor(request, num_bm)
    return processar_alteracao(db, body, autor)


@app.get("/sync")
def sync_status(db: Session = Depends(get_db)):
    dirty = db.query(func.count(Militar.id)).filter(Militar.dirty.is_(True)).scalar() or 0
    return {
        "pending_dirty": dirty,
        "interval_seconds": settings.sync_interval_seconds,
        "last_sync": get_last_sync(),
    }


@app.post("/sync")
def sync_manual():
    """Sincroniza agora: puxa a planilha e grava no Sheets o que está dirty no SQLite."""
    return sync_now()


@app.post("/sync/force", dependencies=[Depends(require_secret)])
def force_sync():
    return sync_now()
