"""
Autenticação do painel admin.

Escolha: sessão server-side (cookie HttpOnly + CSRF), não JWT.
Justificativa: o painel é SSR (Jinja + POST de formulário). Cookie de sessão
não expõe o token ao JavaScript, o CSRF cobre POST e o logout invalida na hora.
JWT em cookie teria os mesmos requisitos de CSRF sem ganho para este caso.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict

import bcrypt
from fastapi import Request
from starlette.responses import Response

from ..config import settings

SESSION_USER_KEY = "admin_user"
SESSION_CSRF_KEY = "csrf_token"

# Rate limit em memória (por processo). Suficiente para um único uvicorn.
_login_hits: dict[str, list[float]] = defaultdict(list)


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def login_permitido(ip: str) -> bool:
    agora = time.time()
    janela = settings.login_rate_window_seconds
    hits = [t for t in _login_hits[ip] if agora - t < janela]
    _login_hits[ip] = hits
    return len(hits) < settings.login_rate_limit


def registrar_tentativa_login(ip: str) -> None:
    _login_hits[ip].append(time.time())


def csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def csrf_ok(request: Request, token: str | None) -> bool:
    esperado = request.session.get(SESSION_CSRF_KEY) or ""
    recebido = token or ""
    return bool(esperado) and hmac.compare_digest(esperado, recebido)


def usuario_sessao(request: Request) -> str | None:
    return request.session.get(SESSION_USER_KEY)


def gravar_sessao(request: Request, username: str) -> None:
    request.session.clear()
    request.session[SESSION_USER_KEY] = username
    request.session[SESSION_CSRF_KEY] = secrets.token_urlsafe(32)


def limpar_sessao(request: Request) -> None:
    request.session.clear()


def fingerprint_autor(request: Request, num_bm: str) -> str:
    """Autor da extensão: Nº BM + hash curto do IP (sem PII completa)."""
    ip = client_ip(request)
    digest = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:8]
    return f"ext:{num_bm}:{digest}"
