"""
Sincronização bidirecional com a aba Relação Nominal.

1) SQLite → planilha: só militares dirty (alterados no formulário/admin).
2) Planilha → SQLite: novos registros e identificação (nome, lotação).
   Campos editáveis de quem está dirty não são sobrescritos pela planilha.
"""
from __future__ import annotations

import logging
import math
import threading
import unicodedata
from urllib.parse import urlparse

import httplib2
import google_auth_httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import settings
from .fields_spec import EPI_ITEM_MAP
from .lookup import bm_base
from .models import SessionLocal, Militar, EpiItem, init_db, utcnow
from .timeutil import agora_br

logger = logging.getLogger("epi.sync")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADER_ROW = 1
DATA_START = 2

_lock = threading.Lock()
_last_sync: dict = {
    "ok": None,
    "at": None,
    "result": None,
    "error": None,
    "sheet": None,
}


def get_last_sync() -> dict:
    return dict(_last_sync)


def _mark_sync(ok: bool, result=None, error=None, sheet=None) -> dict:
    _last_sync.update({
        "ok": ok,
        "at": agora_br().isoformat(),
        "result": result,
        "error": error,
        "sheet": sheet,
    })
    return dict(_last_sync)


# Colunas localizadas pelo texto do cabeçalho (linha 1), não pela posição:
# inserir/mover colunas na planilha não desalinha o sync.
# A coluna A (Nº BM) não tem cabeçalho na planilha, por isso é fixa.
NUM_BM_COL = 0

MILITAR_HEADERS: list[tuple[str, str]] = [
    ("posto_grad",            "P/G"),
    ("descricao_quadro",      "Descrição / Quadro"),
    ("nome_completo",         "Nome completo"),
    ("ativo_inativo",         "Ativo/Inativo"),
    ("situacao_funcional",    "Situação Funcional"),
    ("unidade_principal",     "Unidade Principal"),
    ("unidade_lotacao",       "Unidade / Lotação"),
    ("tam_coturno",           "Tam. Coturno"),
    ("circunferencia_mao_cm", "Circunferência da mão (cm)"),
    ("comprimento_mao_cm",    "Comprimento da mão (cm)"),
    ("altura_cm",             "Altura (cm)"),
    ("peito_cm",              "Peito (cm)"),
    ("cintura_cm",            "Cintura (cm)"),
    ("quadril_cm",            "Quadril (cm)"),
]
# Ausentes em planilhas antigas: sem o cabeçalho, o campo só não é sincronizado.
OPTIONAL_FIELDS = {"circunferencia_mao_cm", "comprimento_mao_cm"}

# Cabeçalho da coluna "possui" de cada item; "Cor" e "Estado de conservação"
# são procurados nas colunas imediatamente seguintes.
EPI_HEADERS: dict[str, str] = {
    "multimissao_conjunto":        "Conjunto Multimissão",
    "multimissao_bota":            "Bota Multimissão",
    "multimissao_capacete":        "Capacete Multimissão",
    "ciurb_capacete_incendio":     "Capacete de Incêndio",
    "ciurb_conjunto":              "Conjunto CIUrb",
    "ciurb_luvas":                 "Luvas CIUrb",
    "ciurb_balaclava":             "Balaclava",
    "outros_luvas_vaqueta":        "Luvas de vaqueta",
    "outros_luvas_csv":            "Luvas CSV",
    "outros_lanterna_cabeca":      "Lanterna de cabeça",
    "outros_oculos_univet":        "Óculos de Ampla Visão (UNIVET)",
    "outros_conjunto_impermeavel": "Conjunto impermeável",
}

FLOAT_FIELDS = {"circunferencia_mao_cm", "comprimento_mao_cm",
                "altura_cm", "peito_cm", "cintura_cm", "quadril_cm"}

# Campos que a planilha pode atualizar mesmo depois do militar editar o form.
IDENT_FIELDS = {
    "posto_grad", "descricao_quadro", "nome_completo",
    "ativo_inativo", "situacao_funcional",
    "unidade_principal", "unidade_lotacao",
}
EDITABLE_FIELDS = {
    "tam_coturno", "circunferencia_mao_cm", "comprimento_mao_cm",
    "altura_cm", "peito_cm", "cintura_cm", "quadril_cm",
}
# Colunas J/K (tamanho de luva) não são lidas nem gravadas.
WRITE_FIELDS = (
    "tam_coturno", "circunferencia_mao_cm", "comprimento_mao_cm",
    "altura_cm", "peito_cm", "cintura_cm", "quadril_cm",
)

POSTO_MAP: dict[str, str] = {
    "SOLDADO": "SD", "SOLDADO DE 1ª CLASSE": "SD", "SOLDADO 1ª CLASSE": "SD",
    "CABO": "CB",
    "3 SARGENTO": "3S", "3º SARGENTO": "3S",
    "2 SARGENTO": "2S", "2º SARGENTO": "2S",
    "1 SARGENTO": "1S", "1º SARGENTO": "1S",
    "SUBTENENTE": "SUBT", "ASPIRANTE": "ASP",
    "2 TENENTE": "2TEN", "2º TENENTE": "2TEN",
    "1 TENENTE": "1TEN", "1º TENENTE": "1TEN",
    "CAPITÃO": "CAP", "CAPITAO": "CAP",
    "MAJOR": "MAJ",
    "TENENTE-CORONEL": "TC", "TENENTE CORONEL": "TC",
    "CORONEL": "CEL",
}


def _proxy_type_http() -> int:
    socks_mod = getattr(httplib2, "socks", None)
    if socks_mod is not None and hasattr(socks_mod, "PROXY_TYPE_HTTP"):
        return socks_mod.PROXY_TYPE_HTTP
    try:
        import socks
        return socks.PROXY_TYPE_HTTP
    except ImportError:
        return 3


def _build_http(creds):
    parsed = urlparse(settings.https_proxy)
    proxy_info = httplib2.ProxyInfo(
        proxy_type=_proxy_type_http(),
        proxy_host=parsed.hostname,
        proxy_port=parsed.port or 8080,
    )
    return google_auth_httplib2.AuthorizedHttp(
        creds, http=httplib2.Http(proxy_info=proxy_info, timeout=60))


def _service(use_proxy: bool):
    creds = service_account.Credentials.from_service_account_file(
        settings.google_credentials_file, scopes=SCOPES)
    if use_proxy and settings.https_proxy:
        return build("sheets", "v4", http=_build_http(creds), cache_discovery=False)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _cell(row: list, idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _parse_float(val) -> float | None:
    """'18,5' / ' 18.5 cm' / '1.234,5' -> float; vazio ou inválido -> None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        n = float(val)
    else:
        s = str(val).strip().lower().replace("cm", "").replace("\xa0", "").replace(" ", "")
        if not s:
            return None
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            n = float(s)
        except ValueError:
            return None
    return n if math.isfinite(n) else None


def _norm_header(s) -> str:
    """Compara cabeçalhos ignorando acento, caixa, espaços e pontuação."""
    s = unicodedata.normalize("NFD", str(s or "")).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def mapear_colunas(header: list) -> tuple[dict[str, int], list[tuple[int, str, str]]]:
    """
    Cabeçalho -> ({campo_militar: col}, [(col, item_key, attr)]).
    Falta de cabeçalho obrigatório aborta: melhor não sincronizar do que gravar na coluna errada.
    """
    pos: dict[str, int] = {}
    for i, h in enumerate(header):
        n = _norm_header(h)
        if n and n not in pos:
            pos[n] = i

    faltando: list[str] = []
    militar = {"num_bm": NUM_BM_COL}
    for campo, titulo in MILITAR_HEADERS:
        i = pos.get(_norm_header(titulo))
        if i is None:
            if campo not in OPTIONAL_FIELDS:
                faltando.append(titulo)
            continue
        militar[campo] = i

    epi: list[tuple[int, str, str]] = []
    for key, titulo in EPI_HEADERS.items():
        h = pos.get(_norm_header(titulo))
        if h is None:
            faltando.append(titulo)
            continue
        epi.append((h, key, "possui"))
        cor = cons = None
        for j in range(h + 1, min(h + 4, len(header))):
            n = _norm_header(header[j])
            if n == "cor" and cor is None:
                cor = j
            elif n == "estadodeconservacao":
                cons = j
                break
        if cons is None:
            faltando.append(f"{titulo} > Estado de conservação")
        else:
            epi.append((cons, key, "conservacao"))
        if EPI_ITEM_MAP.get(key, (None, None))[1] is not None:
            if cor is None:
                faltando.append(f"{titulo} > Cor")
            else:
                epi.append((cor, key, "cor"))

    if faltando:
        raise RuntimeError(
            "Layout da planilha não reconhecido; cabeçalhos ausentes: " + ", ".join(faltando))
    return militar, epi


def _resolve_sheet_title(svc) -> str:
    wanted = (settings.sheet_name or "Relação Nominal").strip()
    meta = svc.spreadsheets().get(spreadsheetId=settings.spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if wanted in titles:
        return wanted
    wnorm = wanted.casefold()
    for t in titles:
        if t.casefold() == wnorm:
            return t
    for t in titles:
        tl = t.casefold()
        if "rela" in tl and "nominal" in tl:
            logger.warning("Aba '%s' não encontrada; usando '%s'", wanted, t)
            return t
    raise RuntimeError(f"Aba '{wanted}' não encontrada. Abas: {titles}")


def _fetch_rows(svc) -> tuple[list[list], str, list]:
    """Lê cabeçalho + dados; colunas extras são ignoradas pelo mapeamento por cabeçalho."""
    title = _resolve_sheet_title(svc)
    resp = svc.spreadsheets().values().get(
        spreadsheetId=settings.spreadsheet_id,
        range=f"'{title}'!A{HEADER_ROW}:CZ",
    ).execute()
    values = resp.get("values", [])
    header = values[0] if values else []
    return values[DATA_START - HEADER_ROW:], title, header


def _col_a1(idx: int) -> str:
    n = idx + 1
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def colunas_escrita(militar_cols: dict[str, int],
                    epi_cols: list[tuple[int, str, str]]) -> dict[int, tuple]:
    """
    Só colunas que o formulário altera. A–H (identificação) e "Aquisição em andamento"
    ficam de fora: na planilha institucional são protegidas (HttpError 400).
    """
    cols: dict[int, tuple] = {
        militar_cols[c]: ("militar", c) for c in WRITE_FIELDS if c in militar_cols}
    for idx, key, attr in epi_cols:
        cols[idx] = ("epi", key, attr)
    return cols


def _faixas(cols: dict[int, tuple]) -> list[tuple[int, int]]:
    """Agrupa colunas consecutivas em faixas (c0, c1) para escrever num único range."""
    out: list[tuple[int, int]] = []
    for c in sorted(cols):
        if out and c == out[-1][1] + 1:
            out[-1] = (out[-1][0], c)
        else:
            out.append((c, c))
    return out


def _valor_celula(m: Militar, alvo: tuple | None):
    if alvo is None:
        return ""
    if alvo[0] == "militar":
        campo = alvo[1]
        v = getattr(m, campo, None)
        if campo in FLOAT_FIELDS:
            if v is None:
                return ""
            try:
                n = float(v)
                return int(n) if n == int(n) else n
            except (TypeError, ValueError):
                return ""
        return "" if v is None else str(v)
    _, item_key, attr = alvo
    item = next((i for i in m.itens if i.item_key == item_key), None)
    if not item:
        return ""
    return getattr(item, attr, None) or ""


def _mapa_linhas(rows: list[list]) -> dict[str, int]:
    """num_bm (e base sem DV) → número da linha na planilha (1-based)."""
    mapa: dict[str, int] = {}
    for i, row in enumerate(rows):
        num = _cell(row, 0)
        if not num:
            continue
        sheet_row = DATA_START + i
        mapa[num] = sheet_row
        base = bm_base(num)
        if base and base not in mapa:
            mapa[base] = sheet_row
    return mapa


def _payloads_militar(m: Militar, sheet_row: int, title: str,
                      cols: dict[int, tuple]) -> list[dict]:
    dados = []
    for c0, c1 in _faixas(cols):
        valores = [_valor_celula(m, cols.get(i)) for i in range(c0, c1 + 1)]
        a1 = f"'{title}'!{_col_a1(c0)}{sheet_row}:{_col_a1(c1)}{sheet_row}"
        dados.append({"range": a1, "majorDimension": "ROWS", "values": [valores]})
    return dados


def _is_protected_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "protected cell" in msg or "protected sheet" in msg or "you are trying to edit a protected" in msg


def _batch_update(svc, data: list[dict]) -> dict:
    """
    Escreve por faixa. Se a planilha bloquear uma faixa, pula e segue.
    Assim uma coluna protegida não impede o restante do push.
    """
    sid = settings.spreadsheet_id
    ok = 0
    skipped: list[str] = []
    for item in data:
        try:
            svc.spreadsheets().values().batchUpdate(
                spreadsheetId=sid,
                body={"valueInputOption": "USER_ENTERED", "data": [item]},
            ).execute()
            ok += 1
        except Exception as exc:
            if _is_protected_error(exc):
                rng = item.get("range", "?")
                logger.warning("Faixa protegida ignorada: %s", rng)
                skipped.append(rng)
                continue
            raise
    return {"ranges_ok": ok, "ranges_protegidas": skipped}


def _push_dirty(svc, rows: list[list], title: str, cols: dict[int, tuple]) -> dict:
    db = SessionLocal()
    enviados = 0
    novos = 0
    protegidas: list[str] = []
    try:
        dirty = db.query(Militar).filter_by(dirty=True).all()
        if not dirty:
            return {"enviados": 0, "novas_linhas": 0, "pendentes": 0, "ranges_protegidas": []}

        mapa = _mapa_linhas(rows)
        updates: list[dict] = []
        appends: list[list] = []
        dirty_ok: list[Militar] = []
        for m in dirty:
            sheet_row = mapa.get(m.num_bm) or mapa.get(bm_base(m.num_bm))
            if sheet_row:
                updates.extend(_payloads_militar(m, sheet_row, title, cols))
                dirty_ok.append(m)
                enviados += 1
            else:
                # Sem linha na planilha: não dá para appendar em aba protegida
                # de forma confiável; mantém dirty para nova tentativa.
                logger.warning(
                    "Militar %s dirty sem linha na planilha; push adiado.",
                    m.num_bm,
                )

        write_stats = {"ranges_ok": 0, "ranges_protegidas": []}
        if updates:
            write_stats = _batch_update(svc, updates)
            protegidas = write_stats.get("ranges_protegidas") or []

        # Só limpa dirty se algo foi escrito ou se não havia faixas a gravar.
        # Se TODAS as faixas estavam protegidas, mantém dirty.
        ranges_ok = int(write_stats.get("ranges_ok") or 0)
        if updates and ranges_ok == 0 and protegidas:
            db.rollback()
            return {
                "enviados": 0,
                "novas_linhas": 0,
                "pendentes": len(dirty),
                "ranges_protegidas": protegidas,
                "error": "Todas as faixas editáveis estão protegidas na planilha.",
            }

        agora = utcnow()
        for m in dirty_ok:
            m.dirty = False
            m.synced_at = agora
        db.commit()
        pendentes = db.query(Militar).filter_by(dirty=True).count()
        return {
            "enviados": enviados if ranges_ok or not updates else 0,
            "novas_linhas": novos,
            "pendentes": pendentes,
            "ranges_ok": ranges_ok,
            "ranges_protegidas": protegidas,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _upsert_rows(rows: list[list], militar_cols: dict[str, int],
                 epi_cols: list[tuple[int, str, str]]) -> dict:
    db = SessionLocal()
    inserted = updated = skipped = 0
    try:
        for row in rows:
            num_bm = _cell(row, NUM_BM_COL)
            if not num_bm:
                skipped += 1
                continue

            dados: dict = {}
            for campo, idx in militar_cols.items():
                raw = _cell(row, idx)
                if campo == "posto_grad":
                    raw = POSTO_MAP.get(raw.upper(), raw)
                if campo in FLOAT_FIELDS:
                    dados[campo] = _parse_float(raw)
                else:
                    dados[campo] = raw

            militar = db.query(Militar).filter_by(num_bm=num_bm).first()
            preservar = bool(militar and militar.dirty)
            if militar is None:
                militar = Militar(**dados, dirty=False)
                db.add(militar)
                db.flush()
                inserted += 1
            else:
                for campo, valor in dados.items():
                    if campo == "num_bm":
                        continue
                    atual = getattr(militar, campo, None)
                    # Planilha vazia não apaga medida/coturno já gravados no SQLite
                    if campo in EDITABLE_FIELDS and valor in (None, "") and atual not in (None, ""):
                        continue
                    if preservar and campo in EDITABLE_FIELDS:
                        continue
                    setattr(militar, campo, valor)
                updated += 1

            militar.synced_at = utcnow()

            itens_raw: dict[str, dict[str, str]] = {}
            for idx, item_key, campo_item in epi_cols:
                itens_raw.setdefault(item_key, {})[campo_item] = _cell(row, idx)

            for item_key, campos in itens_raw.items():
                item = next((i for i in militar.itens if i.item_key == item_key), None)
                if item is None:
                    db.add(EpiItem(
                        militar=militar,
                        item_key=item_key,
                        possui=campos.get("possui", ""),
                        cor=campos.get("cor", ""),
                        conservacao=campos.get("conservacao", ""),
                    ))
                elif not preservar:
                    item.possui = campos.get("possui", item.possui)
                    item.cor = campos.get("cor", item.cor)
                    item.conservacao = campos.get("conservacao", item.conservacao)

        db.commit()
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "rows": len(rows)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _abrir_servico():
    use_proxy = bool(settings.https_proxy)
    try:
        return _service(use_proxy), use_proxy
    except Exception as exc:
        if use_proxy:
            logger.warning("Falha com proxy (%s); tentando conexão direta", exc)
            return _service(use_proxy=False), False
        raise


def sync_from_sheets() -> dict:
    """Alias: ciclo completo (puxa identificação e empurra alterações)."""
    return sync_now()


def sync_now() -> dict:
    """
    1) Planilha → SQLite (não sobrescreve campos dirty).
    2) SQLite dirty → planilha (só o que o usuário/admin alterou).
    """
    if not settings.spreadsheet_id:
        logger.warning("SPREADSHEET_ID não configurado; pulando sync.")
        return _mark_sync(False, error="no_spreadsheet_id")

    if not _lock.acquire(blocking=False):
        logger.info("Sync já em execução; ciclo ignorado.")
        return {"skipped": "already_running", **get_last_sync()}

    try:
        try:
            svc, _ = _abrir_servico()
            rows, title, header = _fetch_rows(svc)
        except Exception as exc:
            if settings.https_proxy:
                logger.warning("Falha com proxy (%s); tentando conexão direta", exc)
                svc = _service(use_proxy=False)
                rows, title, header = _fetch_rows(svc)
            else:
                raise
        logger.info("Sheets: %d linhas lidas da aba '%s'", len(rows), title)

        militar_cols, epi_cols = mapear_colunas(header)
        sem_coluna = sorted(OPTIONAL_FIELDS - militar_cols.keys())
        if sem_coluna:
            logger.warning("Planilha sem coluna para %s; campos não sincronizados.", sem_coluna)

        pull = {"inserted": 0, "updated": 0, "skipped": 0, "rows": len(rows)}
        if rows:
            pull = _upsert_rows(rows, militar_cols, epi_cols)
            logger.info("Pull planilha→DB: %s", pull)

        push = _push_dirty(svc, rows, title, colunas_escrita(militar_cols, epi_cols))
        logger.info("Push DB→planilha: %s", push)

        result = {"pull": pull, "push": push}
        if push.get("error"):
            return _mark_sync(False, result=result, error=push["error"], sheet=title)
        return _mark_sync(True, result=result, sheet=title)

    except Exception as exc:
        logger.exception("Falha no sync bidirecional")
        return _mark_sync(False, error=str(exc))
    finally:
        _lock.release()
