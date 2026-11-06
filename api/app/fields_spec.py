"""
Especificação única dos campos do formulário de EPI.
Reaproveitada pela API (models/schemas/sync) e exportada para o front.

Mantém o domínio em um só lugar para evitar divergência entre
banco, planilha e extensão.
"""

# ---- Opções de selects ----
POSTO_GRAD = [
    ("SD", "Soldado de 1ª Classe"), ("CB", "Cabo"),
    ("3S", "3º Sargento"), ("2S", "2º Sargento"), ("1S", "1º Sargento"),
    ("SUBT", "Subtenente"), ("ASP", "Aspirante"),
    ("2TEN", "2º Tenente"), ("1TEN", "1º Tenente"), ("CAP", "Capitão"),
    ("MAJ", "Major"), ("TC", "Tenente-Coronel"), ("CEL", "Coronel"),
]
COTURNO = [str(n) for n in range(36, 47)]
LUVA = ["5 - XPP", "6 - PP", "7 - P", "8 - M", "9 - G", "10 - GG"]
POSSUI = ["POSSUI", "NÃO POSSUI"]
CONSERVACAO = ["ÓTIMO", "BOM", "RAZOÁVEL", "RUIM"]
COR_CAPACETE = ["AMARELO", "VERMELHO", "BRANCO"]
COR_CONJ_CIURB = ["GOLD", "PRETO"]

# ---- Cabeçalho: dados do militar (não-editáveis no form) ----
# (key, label, type)
MILITAR_READONLY = [
    ("num_bm", "Nº BM", "text"),
    ("posto_grad", "P/G", "select"),
    ("descricao_quadro", "Descrição / Quadro", "text"),
    ("nome_completo", "Nome completo", "text"),
    ("ativo_inativo", "Ativo/Inativo", "text"),
    ("situacao_funcional", "Situação Funcional", "text"),
    ("unidade_principal", "Unidade Principal", "text"),
    ("unidade_lotacao", "Unidade / Lotação", "text"),
]

# ---- Dados gerais (editáveis, colunas diretas no militar) ----
# (key, label, type, options)
DADOS_GERAIS = [
    ("tam_coturno", "Tam. Coturno", "select", COTURNO),
    ("circunferencia_mao_cm", "Circunferência da Mão (cm)", "number", None),
    ("comprimento_mao_cm", "Comprimento da Mão (cm)", "number", None),
    ("altura_cm", "Altura (cm)", "number", None),
    ("peito_cm", "Peito (cm)", "number", None),
    ("cintura_cm", "Cintura (cm)", "number", None),
    ("quadril_cm", "Quadril (cm)", "number", None),
]

# ---- Itens de EPI (tabela filha). Cada item vira 1 linha. ----
# attrs presentes por item: sempre possui/conservacao/aquisicao;
# alguns têm 'cor' (com opções específicas).
# (item_key, grupo, label, cor_options|None)
EPI_ITENS = [
    ("multimissao_conjunto", "MULTIMISSÃO", "Conjunto Multimissão", None),
    ("multimissao_bota", "MULTIMISSÃO", "Bota Multimissão", None),
    ("multimissao_capacete", "MULTIMISSÃO", "Capacete Multimissão", COR_CAPACETE),
    ("ciurb_capacete_incendio", "CIURB", "Capacete de Incêndio", COR_CAPACETE),
    ("ciurb_conjunto", "CIURB", "Conjunto CIUrb", COR_CONJ_CIURB),
    ("ciurb_luvas", "CIURB", "Luvas CIUrb", None),
    ("ciurb_balaclava", "CIURB", "Balaclava", None),
    ("outros_luvas_vaqueta", "OUTROS", "Luvas de vaqueta", None),
    ("outros_luvas_csv", "OUTROS", "Luvas CSV", None),
    ("outros_lanterna_cabeca", "OUTROS", "Lanterna de cabeça", None),
    ("outros_oculos_univet", "OUTROS", "Óculos de Ampla Visão (UNIVET)", None),
    ("outros_conjunto_impermeavel", "OUTROS", "Conjunto impermeável", None),
]

# Mapa rápido item_key -> (label, cor_options)
EPI_ITEM_MAP = {k: (label, cor) for k, _, label, cor in EPI_ITENS}
