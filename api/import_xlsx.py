"""
Importação da planilha "Relação Nominal" → banco SQLite.

Uso (a partir da pasta api/):
    python import_xlsx.py "TESTE NOVO Controle de EPIs - CBMMG.xlsx"

Ou passando o caminho explicitamente:
    python import_xlsx.py /caminho/para/planilha.xlsx

A aba esperada é "Relação Nominal".
Linha 1 = cabeçalho, dados a partir da linha 2.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# Garante que o pacote app/ seja encontrado quando executado direto
sys.path.insert(0, str(Path(__file__).parent))

import openpyxl
from sqlalchemy.orm import Session

from app.models import SessionLocal, Militar, EpiItem, init_db

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SHEET_NAME = "Relação Nominal"
HEADER_ROW = 1   # linha 1 é o cabeçalho
DATA_START  = 2  # dados a partir da linha 2

# Normalização do campo P/G (planilha usa nome por extenso, banco usa código)
POSTO_MAP: dict[str, str] = {
    "SOLDADO":              "SD",
    "SOLDADO DE 1ª CLASSE": "SD",
    "SOLDADO 1ª CLASSE":    "SD",
    "CABO":                 "CB",
    "3 SARGENTO":           "3S",
    "3º SARGENTO":          "3S",
    "2 SARGENTO":           "2S",
    "2º SARGENTO":          "2S",
    "1 SARGENTO":           "1S",
    "1º SARGENTO":          "1S",
    "SUBTENENTE":           "SUBT",
    "ASPIRANTE":            "ASP",
    "2 TENENTE":            "2TEN",
    "2º TENENTE":           "2TEN",
    "1 TENENTE":            "1TEN",
    "1º TENENTE":           "1TEN",
    "CAPITÃO":              "CAP",
    "MAJOR":                "MAJ",
    "TENENTE-CORONEL":      "TC",
    "TENENTE CORONEL":      "TC",
    "CORONEL":              "CEL",
}

# Colunas localizadas pelo cabeçalho, com o mesmo mapeamento do sync online.
from app.sheets_sync import FLOAT_FIELDS, mapear_colunas, _parse_float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell_str(row: tuple, idx: int) -> str:
    """Retorna o valor da célula como string limpa, ou '' se vazia/fora do range."""
    if idx >= len(row):
        return ""
    val = row[idx]
    if val is None:
        return ""
    return str(val).strip()


def _normaliza_posto(raw: str) -> str:
    return POSTO_MAP.get(raw.upper(), raw)


# ---------------------------------------------------------------------------
# Importação principal
# ---------------------------------------------------------------------------

def importar(xlsx_path: str) -> None:
    if not os.path.exists(xlsx_path):
        print(f"[ERRO] Arquivo não encontrado: {xlsx_path}")
        sys.exit(1)

    print(f"Abrindo: {xlsx_path}")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)

    if SHEET_NAME not in wb.sheetnames:
        print(f"[ERRO] Aba '{SHEET_NAME}' não encontrada.")
        print(f"       Abas disponíveis: {wb.sheetnames}")
        sys.exit(1)

    ws = wb[SHEET_NAME]
    header = next(ws.iter_rows(min_row=HEADER_ROW, max_row=HEADER_ROW, values_only=True), ())
    militar_cols, epi_cols = mapear_colunas(list(header))
    rows = list(ws.iter_rows(min_row=DATA_START, values_only=True))
    print(f"Linhas de dados encontradas: {len(rows)}")

    init_db()
    db: Session = SessionLocal()

    inseridos = atualizados = ignorados = 0

    try:
        for line_num, row in enumerate(rows, start=DATA_START):
            num_bm = _cell_str(row, 0)
            if not num_bm:
                ignorados += 1
                continue

            # --- Dados do militar ---
            dados: dict = {}
            for campo, idx in militar_cols.items():
                raw = _cell_str(row, idx)
                if campo == "posto_grad":
                    raw = _normaliza_posto(raw)
                if campo in FLOAT_FIELDS:
                    dados[campo] = _parse_float(raw)
                else:
                    dados[campo] = raw

            # --- Upsert militar ---
            militar = db.query(Militar).filter_by(num_bm=num_bm).first()
            if militar is None:
                militar = Militar(**dados, dirty=True)
                db.add(militar)
                db.flush()   # gera o id
                inseridos += 1
            else:
                for campo, valor in dados.items():
                    setattr(militar, campo, valor)
                militar.dirty = True
                atualizados += 1

            # --- Dados dos itens de EPI ---
            # Agrupa colunas por item_key
            itens_raw: dict[str, dict[str, str]] = {}
            for idx, item_key, campo_item in epi_cols:
                itens_raw.setdefault(item_key, {})[campo_item] = _cell_str(row, idx)

            for item_key, campos in itens_raw.items():
                item = next(
                    (i for i in militar.itens if i.item_key == item_key), None
                )
                if item is None:
                    item = EpiItem(
                        militar=militar,
                        item_key=item_key,
                        possui=campos.get("possui", ""),
                        cor=campos.get("cor", ""),
                        conservacao=campos.get("conservacao", ""),
                    )
                    db.add(item)
                else:
                    item.possui     = campos.get("possui",     item.possui)
                    item.cor        = campos.get("cor",        item.cor)
                    item.conservacao = campos.get("conservacao", item.conservacao)

        db.commit()
        print(f"\nConcluído:")
        print(f"  Inseridos : {inseridos}")
        print(f"  Atualizados: {atualizados}")
        print(f"  Ignorados (sem Nº BM): {ignorados}")

    except Exception as exc:
        db.rollback()
        print(f"[ERRO] Rollback efetuado. Causa: {exc}")
        raise
    finally:
        db.close()
        wb.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # tenta encontrar o .xlsx na mesma pasta
        xlsx_files = list(Path(__file__).parent.glob("*.xlsx"))
        if len(xlsx_files) == 1:
            target = str(xlsx_files[0])
            print(f"Nenhum argumento fornecido. Usando: {target}")
        else:
            print("Uso: python import_xlsx.py <caminho_para_planilha.xlsx>")
            sys.exit(1)
    else:
        target = sys.argv[1]

    importar(target)
