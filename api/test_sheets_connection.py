"""
Teste de conexão com o Google Sheets (independente da API).

Verifica o fluxo de leitura Sheets -> banco, focando na ÚNICA aba relevante:
"Relação Nominal".

Executa 4 verificações em sequência:
  1. Lê o arquivo de credenciais
  2. Autentica com a API do Google
  3. Abre a planilha e confirma que a aba "Relação Nominal" existe
  4. Lê as primeiras linhas da "Relação Nominal" e mostra o mapeamento p/ o banco

Uso (a partir da pasta api/):
    python test_sheets_connection.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file and sets them in os.environ

# ---------------------------------------------------------------------------
# Lê .env manualmente (sem depender do FastAPI/pydantic)
# ---------------------------------------------------------------------------
def load_env(env_path: str = ".env") -> dict[str, str]:
    result = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip()
    except FileNotFoundError:
        print(f"[AVISO] Arquivo {env_path} não encontrado. Usando variáveis de ambiente.")
    return result


CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "app/service_account.json")
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "")
HTTPS_PROXY      = os.getenv("HTTPS_PROXY", "")
PREVIEW_ROWS     = 3   # quantas linhas de dados mostrar no preview


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ok(msg: str)   -> None: print(f"  [OK] {msg}")
def fail(msg: str) -> None: print(f"  [ERRO] {msg}"); sys.exit(1)
def info(msg: str) -> None: print(f"       {msg}")


# ---------------------------------------------------------------------------
# PASSO 1 — Arquivo de credenciais
# ---------------------------------------------------------------------------
print("\n== PASSO 1: Arquivo de credenciais ==")
creds_path = Path(CREDENTIALS_FILE)
if not creds_path.exists():
    fail(f"Arquivo não encontrado: {creds_path.resolve()}\n"
         f"       Verifique GOOGLE_CREDENTIALS_FILE no .env")
ok(f"Arquivo encontrado: {creds_path.resolve()}")

import json
try:
    with open(creds_path, encoding="utf-8") as f:
        creds_data = json.load(f)
    client_email = creds_data.get("client_email", "—")
    project_id   = creds_data.get("project_id", "—")
    ok(f"JSON válido")
    info(f"client_email : {client_email}")
    info(f"project_id   : {project_id}")
except json.JSONDecodeError as e:
    fail(f"JSON inválido: {e}")


# ---------------------------------------------------------------------------
# PASSO 2 — Autenticação
# ---------------------------------------------------------------------------
print("\n== PASSO 2: Autenticação Google ==")
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    fail("Pacotes Google não instalados. Rode: pip install google-api-python-client google-auth")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
try:
    creds = service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES)
    ok("Credenciais carregadas com sucesso")
except Exception as e:
    fail(f"Erro ao carregar credenciais: {e}")

# Configura proxy se definido no .env
authorized_http = None
if HTTPS_PROXY:
    try:
        from urllib.parse import urlparse
        import httplib2
        import google_auth_httplib2
        socks_mod = getattr(httplib2, "socks", None)
        if socks_mod is not None and hasattr(socks_mod, "PROXY_TYPE_HTTP"):
            proxy_type = socks_mod.PROXY_TYPE_HTTP
        else:
            try:
                import socks
                proxy_type = socks.PROXY_TYPE_HTTP
            except ImportError:
                proxy_type = 3
        parsed = urlparse(HTTPS_PROXY)
        proxy_info = httplib2.ProxyInfo(
            proxy_type=proxy_type,
            proxy_host=parsed.hostname,
            proxy_port=parsed.port or 8080,
        )
        authorized_http = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(proxy_info=proxy_info))
        info(f"Proxy configurado: {HTTPS_PROXY}")
    except Exception as e:
        fail(f"Erro ao configurar proxy: {e}")
else:
    info("Sem proxy (conexão direta)")

try:
    if authorized_http:
        svc = build("sheets", "v4", http=authorized_http, cache_discovery=False)
    else:
        svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    ok("Conexão com a API Google Sheets estabelecida")
except Exception as e:
    fail(f"Erro ao conectar com a API: {e}")


# ---------------------------------------------------------------------------
# PASSO 3 — Abre a planilha e lista abas
# ---------------------------------------------------------------------------
print("\n== PASSO 3: Abrindo a planilha ==")
if not SPREADSHEET_ID:
    fail("SPREADSHEET_ID não definido no .env")
info(f"SPREADSHEET_ID: {SPREADSHEET_ID}")

try:
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    title = meta.get("properties", {}).get("title", "—")
    sheets = [s["properties"]["title"] for s in meta.get("sheets", [])]
    ok(f"Planilha acessada: \"{title}\"")
    info(f"Abas encontradas ({len(sheets)}): {sheets}")
except Exception as e:
    fail(
        f"Erro ao acessar a planilha: {e}\n"
        f"       Verifique:\n"
        f"         1. SPREADSHEET_ID correto no .env\n"
        f"         2. Planilha compartilhada com: {client_email}"
    )


# ---------------------------------------------------------------------------
# PASSO 4 — Lê prévia da aba "Relação Nominal" (única relevante)
# ---------------------------------------------------------------------------
ABA_RELACAO = "Relação Nominal"

print(f"\n== PASSO 4: Prévia da aba \"{ABA_RELACAO}\" "
      f"(primeiras {PREVIEW_ROWS} linhas de dados) ==")

if ABA_RELACAO not in sheets:
    fail(f"A aba \"{ABA_RELACAO}\" não existe na planilha. "
         f"É a única aba lida pelo sync. Abas disponíveis: {sheets}")

vs = svc.spreadsheets().values()

# Mapeamento (espelha sheets_sync.py): col_idx 0-based -> campo do militar
MILITAR_PREVIEW = [
    (0, "num_bm"), (1, "posto_grad"), (3, "nome_completo"), (4, "ativo_inativo"),
]
# Demais colunas localizadas pelo cabeçalho (como no sync): cabeçalho -> rótulo
HEADER_PREVIEW = [
    ("Circunferência da mão (cm)", "circunferencia_mao_cm"),
    ("Comprimento da mão (cm)", "comprimento_mao_cm"),
    ("Altura (cm)", "altura_cm"),
    ("Conjunto Multimissão", "multimissao_conjunto.possui"),
    ("Conjunto impermeável", "outros_conjunto_impermeavel.possui"),
]


def _cell(row: list, idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""


def _norm_header(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", str(s or "")).casefold()
    return "".join(ch for ch in s if ch.isalnum())


try:
    resp = vs.get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{ABA_RELACAO}'!A1:CZ{1 + PREVIEW_ROWS}"
    ).execute()
    rows = resp.get("values", [])
    if not rows:
        fail("Aba vazia — nada para sincronizar.")

    header = rows[0]
    info(f"Cabeçalho: {len(header)} colunas")
    pos = {}
    for j, h in enumerate(header):
        pos.setdefault(_norm_header(h), j)
    for titulo, rotulo in HEADER_PREVIEW:
        if _norm_header(titulo) not in pos:
            info(f"[AVISO] Cabeçalho não encontrado: {titulo!r} ({rotulo})")

    data_rows = rows[1:]
    info(f"Linhas de dados na prévia: {len(data_rows)}")

    for i, row in enumerate(data_rows, start=2):
        num_bm = _cell(row, 0)
        if not num_bm:
            info(f"Linha {i}: (sem Nº BM — seria ignorada)")
            continue
        print(f"\n  --- Linha {i} (mapeada para o banco) ---")
        for idx, campo in MILITAR_PREVIEW:
            info(f"militar.{campo:<16} = {_cell(row, idx)!r}")
        for titulo, rotulo in HEADER_PREVIEW:
            idx = pos.get(_norm_header(titulo))
            if idx is not None:
                info(f"{rotulo:<39} = {_cell(row, idx)!r}")
except Exception as e:
    fail(f"Erro ao ler a aba \"{ABA_RELACAO}\": {e}")

# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("  Conexão OK! O sync está pronto para ler do Sheets e gravar no banco.")
print(f"  Fonte (única aba lida): \"{ABA_RELACAO}\"")
print("  Destino: SQLite (tabelas 'militar' e 'militar_epi_item').")
print("=" * 60 + "\n")
