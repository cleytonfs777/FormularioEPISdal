/* ============================================================================
   CBMMG - Formulário EPIs (LOIQ / SIGPBI)
   - Content script (Manifest V3), roda em todos os frames.
   - Só injeta se a página/frame contiver um <a title="AADP">.
   - Clona uma aba existente (padrão classe "ativada", li + a) e adiciona
     a aba "Formulário EPIs"; o conteúdo alterna no padrão tabOculta/tabVisivel.
   - As abas nativas continuam funcionando normalmente; a nova só mostra o form.
   - Envio: valida, envia só o diff para /api/alteracoes.
   - Imagens de instrução carregadas via chrome.runtime.getURL (manual/*.png).
   ========================================================================== */
(() => {
  "use strict";

  const CLASSE_ATIVA = "ativada";
  const ROOT_ID = "td_conteudo_epi";
  const ABA_ID = "td_borda_def.tab.custom_epi";

  // Dependem da ordem das seções/campos em montarHtmlFormulario (Dados Gerais = 2ª seção).
  const SEL_CIRCUNFERENCIA_MAO = "#cbmmg-epi-root > div > div:nth-child(2) > div > div > div:nth-child(2) > input[type=text]";
  const SEL_COMPRIMENTO_MAO = "#cbmmg-epi-root > div > div:nth-child(2) > div > div > div:nth-child(3) > input[type=text]";
  const SEL_MAO = {
    circunferencia_mao_cm: SEL_CIRCUNFERENCIA_MAO,
    comprimento_mao_cm: SEL_COMPRIMENTO_MAO,
  };

  // ---- Opções ---------------------------------------------------------------
  const OPT_PG = [
    ["SD", "SD - Soldado de 1ª Classe"], ["CB", "CB - Cabo"],
    ["3S", "3S - 3º Sargento"], ["2S", "2S - 2º Sargento"], ["1S", "1S - 1º Sargento"],
    ["SUBT", "SUBT - Subtenente"], ["ASP", "ASP - Aspirante"],
    ["2TEN", "2TEN - 2º Tenente"], ["1TEN", "1TEN - 1º Tenente"], ["CAP", "CAP - Capitão"],
    ["MAJ", "MAJ - Major"], ["TC", "TC - Tenente-Coronel"], ["CEL", "CEL - Coronel"],
  ];
  const OPT_COTURNO = ["36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46"];
  const OPT_POSSUI = ["POSSUI", "NÃO POSSUI"];
  const OPT_CONSERV = ["ÓTIMO", "BOM", "RAZOÁVEL", "RUIM"];
  const OPT_COR_CAP = ["AMARELO", "VERMELHO", "BRANCO"];
  const OPT_COR_CIURB = ["GOLD", "PRETO"];

  // ---- Campos ---------------------------------------------------------------
  const READONLY = [
    { key: "num_bm", label: "Nº BM", type: "text" },
    { key: "posto_grad", label: "P/G", type: "select", options: OPT_PG },
    { key: "descricao_quadro", label: "Descrição / Quadro", type: "text" },
    { key: "nome_completo", label: "Nome completo", type: "text" },
    { key: "ativo_inativo", label: "Ativo/Inativo", type: "text" },
    { key: "situacao_funcional", label: "Situação Funcional", type: "text" },
    { key: "unidade_principal", label: "Unidade Principal", type: "text" },
    { key: "unidade_lotacao", label: "Unidade / Lotação", type: "text" },
  ];

  const DADOS_GERAIS = [
    { key: "tam_coturno", label: "Tam. Coturno", type: "select", options: OPT_COTURNO },
    { key: "circunferencia_mao_cm", label: "Circunferência da Mão (cm)", type: "text" },
    { key: "comprimento_mao_cm", label: "Comprimento da Mão (cm)", type: "text" },
    { key: "altura_cm", label: "Altura (cm)", type: "number" },
    { key: "peito_cm", label: "Peito (cm)", type: "number" },
    { key: "cintura_cm", label: "Cintura (cm)", type: "number" },
    { key: "quadril_cm", label: "Quadril (cm)", type: "number" },
  ];

  // Campo -> imagem de instrução (arquivo relativo dentro da extensão)
  const INFO_IMAGES = {
    "circunferencia_mao_cm": "manual/circunferencia_mao.png",
    "comprimento_mao_cm": "manual/comprimento_mao.png",
    "altura_cm": "manual/altura.png",
    "peito_cm": "manual/largura.png",
    "cintura_cm": "manual/cintura.png",
    "quadril_cm": "manual/quadril.png",
  };

  const GRUPOS = [
    {
      titulo: "MULTIMISSÃO", itens: [
        { key: "multimissao_conjunto", label: "Conjunto Multimissão", cor: null },
        { key: "multimissao_bota", label: "Bota Multimissão", cor: null },
        { key: "multimissao_capacete", label: "Capacete Multimissão", cor: OPT_COR_CAP },
      ]
    },
    {
      titulo: "CIURB", itens: [
        { key: "ciurb_capacete_incendio", label: "Capacete de Incêndio", cor: OPT_COR_CAP },
        { key: "ciurb_conjunto", label: "Conjunto CIUrb", cor: OPT_COR_CIURB },
        { key: "ciurb_luvas", label: "Luvas CIUrb", cor: null },
        { key: "ciurb_balaclava", label: "Balaclava", cor: null },
      ]
    },
    {
      titulo: "OUTROS", itens: [
        { key: "outros_luvas_vaqueta", label: "Luvas de vaqueta", cor: null },
        { key: "outros_luvas_csv", label: "Luvas CSV", cor: null },
        { key: "outros_lanterna_cabeca", label: "Lanterna de cabeça", cor: null },
        { key: "outros_oculos_univet", label: "Óculos de Ampla Visão (UNIVET)", cor: null },
        { key: "outros_conjunto_impermeavel", label: "Conjunto impermeável", cor: null },
      ]
    },
  ];

  const DG_LABEL = Object.fromEntries(DADOS_GERAIS.map(f => [f.key, f.label]));
  const ITEM_LABEL = {};
  GRUPOS.forEach(g => g.itens.forEach(i => { ITEM_LABEL[i.key] = i.label; }));

  const FLOAT_KEYS = new Set([
    "circunferencia_mao_cm", "comprimento_mao_cm",
    "altura_cm", "peito_cm", "cintura_cm", "quadril_cm"
  ]);

  const PG_ALIAS = {
    SD: "SD", SOLDADO: "SD", "SOLDADO DE 1A CLASSE": "SD",
    CB: "CB", CABO: "CB",
    "3S": "3S", "3 SARGENTO": "3S", "3O SARGENTO": "3S", "TERCEIRO SARGENTO": "3S",
    "2S": "2S", "2 SARGENTO": "2S", "2O SARGENTO": "2S", "SEGUNDO SARGENTO": "2S",
    "1S": "1S", "1 SARGENTO": "1S", "1O SARGENTO": "1S", "PRIMEIRO SARGENTO": "1S",
    SARGENTO: "1S",
    SUBT: "SUBT", SUBTENENTE: "SUBT",
    ASP: "ASP", ASPIRANTE: "ASP",
    "2TEN": "2TEN", "2 TENENTE": "2TEN", "2O TENENTE": "2TEN", "SEGUNDO TENENTE": "2TEN",
    "1TEN": "1TEN", "1 TENENTE": "1TEN", "1O TENENTE": "1TEN", "PRIMEIRO TENENTE": "1TEN",
    TENENTE: "1TEN",
    CAP: "CAP", CAPITAO: "CAP",
    MAJ: "MAJ", MAJOR: "MAJ",
    TC: "TC", "TENENTE-CORONEL": "TC", "TENENTE CORONEL": "TC",
    CEL: "CEL", CORONEL: "CEL",
  };

  function normTxt(s) {
    return String(s || "").trim().toUpperCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ");
  }

  function mapPostoGrad(apiVal) {
    const raw = normTxt(apiVal);
    if (!raw) return "";
    if (PG_ALIAS[raw]) return PG_ALIAS[raw];
    const byVal = OPT_PG.find(([v]) => v === raw);
    if (byVal) return byVal[0];
    const byLabel = OPT_PG.find(([, lbl]) => normTxt(lbl).includes(raw) || raw.includes(normTxt(lbl.split(" - ")[0])));
    if (byLabel) return byLabel[0];
    for (const k of Object.keys(PG_ALIAS)) {
      if (raw.includes(k) || k.includes(raw)) return PG_ALIAS[k];
    }
    return "";
  }

  function limparNumero(txt) {
    return String(txt || "").replace(/\s+/g, "").trim();
  }

  function extrairNumero(doc) {
    if (!doc) return "";
    const sels = [
      "#def\\.tab\\.automatico_0_corpo > table.delimitador.tabelaFormulario > tbody > tr:nth-child(1) > td:nth-child(1) > span:nth-child(2) > span",
      "table.delimitador.tabelaFormulario tbody tr:nth-child(1) td:nth-child(1) span:nth-child(2) > span",
    ];
    for (let i = 0; i < sels.length; i++) {
      try {
        const el = doc.querySelector(sels[i]);
        const n = limparNumero(el && el.textContent);
        if (n) return n;
      } catch (_) { /* selector inválido */ }
    }
    try {
      const corpo = doc.getElementById("def.tab.automatico_0_corpo")
        || doc.querySelector('[id*="tab.automatico"][id$="_corpo"]');
      if (corpo) {
        const el = corpo.querySelector("table.tabelaFormulario tbody tr td span span");
        const n = limparNumero(el && el.textContent);
        if (n) return n;
      }
    } catch (_) { /* ignore */ }
    return "";
  }

  function extrairNumeroAmplo(doc) {
    let n = extrairNumero(doc);
    if (n) return n;
    try {
      if (window.top && window.top.document) n = extrairNumero(window.top.document);
      if (n) return n;
    } catch (_) { /* cross-origin */ }
    try {
      const w = doc.defaultView || window;
      for (let i = 0; i < w.frames.length; i++) {
        try {
          n = extrairNumero(w.frames[i].document);
          if (n) return n;
        } catch (_) { /* cross-origin frame */ }
      }
    } catch (_) { /* ignore */ }
    return "";
  }

  // ---- Helpers --------------------------------------------------------------
  function imgUrl(rel) {
    try { return chrome.runtime.getURL(rel); } catch (_) { return rel; }
  }

  function forceStyle(el, props) {
    Object.keys(props).forEach(function (k) { el.style.setProperty(k, props[k], "important"); });
  }

  let ignoreCloseUntil = 0;

  function fecharInfoModal(fromDoc) {
    const docs = [fromDoc, document];
    docs.forEach(function (d) {
      if (!d) return;
      try {
        const el = d.getElementById("epi-info-overlay-root");
        if (el && el.parentNode) el.parentNode.removeChild(el);
      } catch (_) { /* ignore */ }
    });
  }

  function abrirInfoModal(key, fromDoc) {
    const rel = INFO_IMAGES[key];
    console.log("[EPI] abrirInfoModal", key, rel);
    if (!rel) { console.warn("[EPI] sem imagem para", key); return; }

    // Sempre no mesmo documento do botão. Overlay no window.top NÃO cobre
    // o conteúdo de <frame>/<iframe> (frameset do SIGPBI).
    const doc = fromDoc || document;
    fecharInfoModal(doc);

    const ov = doc.createElement("div");
    ov.id = "epi-info-overlay-root";
    forceStyle(ov, {
      display: "flex",
      position: "fixed",
      top: "0", right: "0", bottom: "0", left: "0",
      width: "100%", height: "100%",
      margin: "0", padding: "16px",
      border: "0",
      "z-index": "2147483647",
      background: "rgba(0,0,0,0.55)",
      "align-items": "center",
      "justify-content": "center",
      opacity: "1",
      visibility: "visible",
      "pointer-events": "auto",
      transform: "none",
      "box-sizing": "border-box"
    });

    const box = doc.createElement("div");
    forceStyle(box, {
      background: "#fff",
      "border-radius": "12px",
      padding: "20px 24px",
      "max-width": "760px",
      width: "95%",
      "max-height": "90vh",
      overflow: "auto",
      "box-shadow": "0 8px 32px rgba(0,0,0,.3)",
      "box-sizing": "border-box",
      "font-family": "system-ui,sans-serif",
      color: "#111827"
    });

    const hd = doc.createElement("div");
    forceStyle(hd, {
      display: "flex",
      "justify-content": "space-between",
      "align-items": "center",
      "margin-bottom": "12px"
    });

    const title = doc.createElement("div");
    title.textContent = "Instrução de Medida — " + (DG_LABEL[key] || key);
    forceStyle(title, { margin: "0", "font-size": "1.1rem", "font-weight": "600", color: "#1e293b" });

    const closeBtn = doc.createElement("span");
    closeBtn.textContent = "\u00d7";
    closeBtn.title = "Fechar";
    forceStyle(closeBtn, {
      cursor: "pointer",
      "font-size": "1.8rem",
      "line-height": "1",
      color: "#64748b",
      padding: "0 4px",
      "user-select": "none"
    });

    const canvas = doc.createElement("canvas");
    forceStyle(canvas, {
      display: "block",
      width: "100%",
      "max-height": "70vh",
      background: "#f8fafc",
      "border-radius": "8px"
    });

    const err = doc.createElement("div");
    forceStyle(err, { color: "#b91c1c", "font-size": "0.9rem", "margin-top": "8px", display: "none" });

    hd.appendChild(title);
    hd.appendChild(closeBtn);
    box.appendChild(hd);
    box.appendChild(canvas);
    box.appendChild(err);
    ov.appendChild(box);

    const fechar = function (e) {
      if (Date.now() < ignoreCloseUntil) return;
      if (e) { e.preventDefault(); e.stopPropagation(); }
      fecharInfoModal(doc);
    };
    closeBtn.addEventListener("click", fechar, true);
    ov.addEventListener("click", function (e) { if (e.target === ov) fechar(e); }, true);

    (doc.body || doc.documentElement).appendChild(ov);

    fetch(imgUrl(rel))
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
      .then(function (blob) { return createImageBitmap(blob); })
      .then(function (bmp) {
        canvas.width = bmp.width;
        canvas.height = bmp.height;
        canvas.getContext("2d").drawImage(bmp, 0, 0);
        forceStyle(canvas, { width: "100%", height: "auto", "max-height": "70vh" });
      })
      .catch(function (e) {
        console.error("[EPI] falha ao carregar imagem:", rel, e);
        err.textContent = "Não foi possível carregar a imagem de instrução.";
        forceStyle(err, { display: "block" });
      });
  }

  function findInfoBtn(target) {
    if (!target) return null;
    if (target.nodeType !== 1) target = target.parentElement;
    if (!target) return null;
    if (typeof target.closest === "function") return target.closest(".epi-info-btn");
    while (target) {
      if (target.classList && target.classList.contains("epi-info-btn")) return target;
      target = target.parentElement;
    }
    return null;
  }

  function onInfoEvent(e) {
    try {
      const btn = findInfoBtn(e.target);
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      if (typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation();
      ignoreCloseUntil = Date.now() + 600;
      abrirInfoModal(btn.getAttribute("data-info-key"), btn.ownerDocument);
    } catch (err) {
      console.error("[EPI] onInfoEvent", err);
    }
  }

  // Só "click": abrir no pointerdown fazia o mouseup/click seguinte
  // acertar o backdrop e fechar o modal na hora.
  window.addEventListener("click", onInfoEvent, true);
  document.addEventListener("click", onInfoEvent, true);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") fecharInfoModal(document);
    if ((e.key === "Enter" || e.key === " ") && findInfoBtn(e.target)) {
      e.preventDefault();
      ignoreCloseUntil = Date.now() + 600;
      abrirInfoModal(e.target.getAttribute("data-info-key") || findInfoBtn(e.target).getAttribute("data-info-key"), document);
    }
  }, true);

  function selHtml(arr, sel, attrs) {
    const o = arr.map(v => {
      const [val, lbl] = Array.isArray(v) ? v : [v, v];
      return '<option value="' + val + '" ' + (val === sel ? "selected" : "") + '>' + lbl + '</option>';
    }).join("");
    return '<select ' + attrs + '><option value="">Selecione</option>' + o + '</select>';
  }

  const INP_STYLE = 'width:100%;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;'
    + 'font-size:0.875rem;box-sizing:border-box;background:#fff;color:#111827;';
  const RO_STYLE = INP_STYLE + 'background:#f3f4f6;';

  function fieldWrap(label, ctrl, infoBtn, required) {
    const star = required ? ' <span style="color:#dc2626;">*</span>' : '';
    return '<div style="display:flex;flex-direction:column;gap:4px;">'
      + '<div style="display:flex;align-items:center;font-size:0.8rem;color:#374151;font-weight:500;">'
      + '<span>' + label + star + '</span>' + (infoBtn || '')
      + '</div>' + ctrl
      + '</div>';
  }

  function createSection(title, contentHtml) {
    return '<div style="border:1px solid #e5e7eb;border-radius:12px;background:#fff;margin-bottom:16px;">'
      + '<header style="padding:16px 24px;border-bottom:1px solid #e5e7eb;">'
      + '<h3 style="margin:0;font-size:1rem;font-weight:600;color:#111827;">' + title + '</h3>'
      + '</header>'
      + '<div style="padding:24px;">'
      + '<div class="epi-grid-3" style="display:grid;gap:16px;">'
      + contentHtml
      + '</div>'
      + '</div>'
      + '</div>';
  }

  // ---- Localiza documento correto (página ou frame com AADP) ----------------
  function temAADP(d) {
    try { return !!d.querySelector('a[title="AADP"]'); } catch (_) { return false; }
  }

  // ---- Monta o HTML do formulário -------------------------------------------
  function montarHtmlFormulario() {
    const roHtml = READONLY.map(f => {
      const ctrl = f.type === "select"
        ? selHtml(f.options, "", 'data-ro="' + f.key + '" disabled style="' + RO_STYLE + '"')
        : '<input type="text" data-ro="' + f.key + '" readonly style="' + RO_STYLE + '">';
      return fieldWrap(f.label, ctrl, "", false);
    }).join("");

    const dgHtml = DADOS_GERAIS.map(f => {
      const ctrl = f.type === "select"
        ? selHtml(f.options, "", 'data-dg="' + f.key + '" style="' + INP_STYLE + '"')
        : f.type === "number"
          ? '<input type="number" step="0.1" data-dg="' + f.key + '" style="' + INP_STYLE + '">'
          : '<input type="text" data-dg="' + f.key + '" style="' + INP_STYLE + '">';
      const infoBtn = INFO_IMAGES[f.key]
        ? '<span class="epi-info-btn" data-info-key="' + f.key + '" title="Como medir" role="button" tabindex="0" '
        + 'style="background:#eff6ff;border:1px solid #3b82f6;color:#1d4ed8;border-radius:50%;width:20px;height:20px;'
        + 'font-size:12px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;margin-left:6px;'
        + 'padding:0;line-height:1;flex-shrink:0;user-select:none;">&#8505;</span>'
        : "";
      return fieldWrap(f.label, ctrl, infoBtn, true);
    }).join("");

    const gruposHtml = GRUPOS.map(g => {
      const cards = g.itens.map(item => {
        let campos = fieldWrap("Possui?",
          selHtml(OPT_POSSUI, "", 'data-item="' + item.key + '" data-attr="possui" style="' + INP_STYLE + '"'), "", false);
        if (item.cor) {
          campos += fieldWrap("Cor",
            selHtml(item.cor, "", 'data-item="' + item.key + '" data-attr="cor" style="' + INP_STYLE + '"'), "", false);
        }
        campos += fieldWrap("Estado de conservação",
          selHtml(OPT_CONSERV, "", 'data-item="' + item.key + '" data-attr="conservacao" disabled style="' + INP_STYLE + '"'), "", false);
        const justifHtml = '<div class="epi-justificativa-box" data-item="' + item.key + '" style="display:none;margin-top:12px;padding:12px;background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;">'
          + '<label style="display:block;font-size:12px;font-weight:600;color:#9a3412;margin-bottom:6px;">'
          + 'Justificativa para alteração de posse (Obrigatório para aprovação):'
          + '</label>'
          + '<textarea data-item="' + item.key + '" data-attr="justificativa" placeholder="Informe o motivo de alterar para NÃO POSSUI (ex.: recolhido pela OBM, extraviado, danificado sem reposição)..." '
          + 'style="width:100%;min-height:55px;"></textarea>'
          + '</div>';
        return '<div data-card="' + item.key + '" style="grid-column:1/-1;border:1px solid #e5e7eb;background:#f9fafb;border-radius:8px;padding:16px;">'
          + '<h4 style="margin:0 0 12px;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:0.03em;color:#111827;">' + item.label + '</h4>'
          + '<div class="epi-grid-3" style="display:grid;gap:12px;">' + campos + '</div>'
          + justifHtml
          + '</div>';
      }).join("");
      return createSection(g.titulo, cards);
    }).join("");

    return '<div id="cbmmg-epi-root" style="padding:16px;font-family:system-ui,sans-serif;color:#111827;">'
      // Modal de erros (o de instrução é criado à parte, fora do form — ver criarInfoModal)
      + '<div id="epi-modal-overlay" style="display:none;position:fixed;top:0;right:0;bottom:0;left:0;z-index:99999;background:rgba(0,0,0,.45);align-items:center;justify-content:center;">'
      + '<div style="background:#fff;border-radius:8px;padding:24px 28px;max-width:460px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,.25);">'
      + '<p id="epi-modal-title" style="margin:0 0 8px;font-weight:700;font-size:1.05rem;">Aviso</p>'
      + '<div id="epi-modal-body" style="margin-bottom:16px;font-size:.95rem;line-height:1.5;"></div>'
      + '<div style="display:flex;gap:8px;justify-content:flex-end;">'
      + '<span id="epi-modal-ok" role="button" tabindex="0" style="padding:8px 22px;border-radius:6px;border:none;background:#b71c1c;color:#fff;cursor:pointer;font-weight:600;display:inline-block;user-select:none;">OK</span>'
      + '</div>'
      + '</div>'
      + '</div>'
      // Confirmação das alterações antes do envio
      + '<div id="epi-confirm-overlay" style="display:none;position:fixed;top:0;right:0;bottom:0;left:0;z-index:99999;background:rgba(0,0,0,.45);align-items:center;justify-content:center;">'
      + '<div style="background:#fff;border-radius:8px;padding:24px 28px;max-width:560px;width:92%;box-shadow:0 8px 32px rgba(0,0,0,.25);font-family:system-ui,sans-serif;color:#111827;">'
      + '<p style="margin:0 0 8px;font-weight:700;font-size:1.05rem;">Confirmar alterações</p>'
      + '<p style="margin:0 0 10px;font-size:.9rem;color:#374151;">Revise os campos alterados antes de enviar:</p>'
      + '<div id="epi-confirm-body" style="max-height:50vh;overflow:auto;margin-bottom:16px;font-size:.9rem;line-height:1.5;"></div>'
      + '<div style="display:flex;gap:8px;justify-content:flex-end;">'
      + '<span id="epi-confirm-cancelar" role="button" tabindex="0" style="padding:8px 18px;border-radius:6px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer;font-weight:600;display:inline-block;user-select:none;">Cancelar</span>'
      + '<span id="epi-confirm-ok" role="button" tabindex="0" style="padding:8px 18px;border-radius:6px;border:none;background:#b71c1c;color:#fff;cursor:pointer;font-weight:600;display:inline-block;user-select:none;">Confirmar e enviar</span>'
      + '</div>'
      + '</div>'
      + '</div>'
      // Termo de veracidade (1ª abertura)
      + '<div id="epi-termo-overlay" style="display:none;position:fixed;top:0;right:0;bottom:0;left:0;z-index:2147483646;background:rgba(15,23,42,.72);align-items:center;justify-content:center;">'
      + '<div style="background:#fff;border-radius:12px;padding:28px 32px;max-width:640px;width:94%;max-height:90vh;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.35);font-family:system-ui,sans-serif;color:#111827;">'
      + '<h3 style="margin:0 0 12px;font-size:1.05rem;font-weight:700;color:#7f1d1d;letter-spacing:.02em;">TERMO DE RESPONSABILIDADE E VERACIDADE</h3>'
      + '<div style="font-size:.9rem;line-height:1.55;color:#1f2937;text-align:justify;">'
      + '<p style="margin:0 0 12px;">Ao iniciar o preenchimento deste formulário, o militar declara estar ciente de que todas as informações prestadas devem refletir a estrita expressão da verdade. Os dados aqui inseridos possuem caráter de documento oficial e são o fundamento técnico para o planejamento logístico, distribuição e aquisição de Equipamentos de Proteção Individual pelo Corpo de Bombeiros Militar de Minas Gerais.</p>'
      + '<p style="margin:0 0 16px;">Fica o usuário expressamente advertido de que a inserção de informações falsas, a omissão de dados ou a declaração inverídica sobre o estado ou a posse de EPIs constituem infrações administrativas e disciplinares. Tais atos sujeitam o autor às sanções previstas no Código de Ética e Disciplina, sem prejuízo da responsabilização penal militar correspondente, notadamente no que tange ao crime de falsidade ideológica previsto no Código Penal Militar.</p>'
      + '</div>'
      + '<div id="epi-termo-check" role="checkbox" aria-checked="false" tabindex="0" '
      + 'style="display:flex;gap:10px;align-items:flex-start;font-size:.9rem;font-weight:600;cursor:pointer;margin:8px 0 18px;user-select:none;">'
      + '<span class="epi-termo-box" style="width:20px;height:20px;border:2px solid #b71c1c;border-radius:4px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;background:#fff;color:#fff;font-size:14px;line-height:1;margin-top:1px;"></span>'
      + '<span>Li, compreendi e atesto a veracidade das informações que serão inseridas.</span>'
      + '</div>'
      + '<div style="display:flex;justify-content:flex-end;">'
      + '<span id="epi-termo-ok" role="button" tabindex="0" style="padding:8px 22px;border-radius:8px;border:none;background:#9ca3af;color:#fff;font-weight:600;cursor:not-allowed;display:inline-block;">Concordo e continuar</span>'
      + '</div>'
      + '</div>'
      + '</div>'
      // Corpo
      + '<div>'
      + createSection("Identificação", roHtml)
      + createSection("Dados Gerais", dgHtml)
      + gruposHtml
      + '<div id="epi-avisos-gerais" style="display:none;margin-bottom:16px;padding:12px 16px;border:1px solid #e5e7eb;border-radius:12px;background:#fff;">'
      + '<span style="font-weight:600;font-size:.9rem;">Avisos</span>'
      + '</div>'
      + '<div style="display:flex;justify-content:flex-end;align-items:center;margin-top:8px;gap:12px;flex-wrap:wrap;">'
      + '<span id="epi-status" style="font-size:.875rem;font-weight:600;margin-right:auto;"></span>'
      + '<span id="epi-enviar" role="button" tabindex="0" title="Enviar Formulário" '
      + 'style="background:#b71c1c;color:#fff;padding:.55rem 1.5rem;border-radius:.5rem;font-weight:600;cursor:pointer;'
      + 'border:none;display:inline-block;user-select:none;pointer-events:auto;">Enviar Formulário</span>'
      + '</div>'
      + '</div>'
      + '</div>';
  }

  // ---- Injeta a aba + painel ------------------------------------------------
  function injetar(doc) {
    // idempotência (getElementById usa o id cru; o ponto não precisa de escape aqui)
    if (doc.getElementById(ABA_ID)) return;

    const abaModelo =
      doc.querySelector('li[id*="tab.automatico"]')
      || doc.querySelector('[id*="tab"][id*="automatico"]')
      || doc.querySelector('a[title="AADP"]')?.closest("li");
    if (!abaModelo) return;

    const barra = abaModelo.parentNode;

    // Clona a aba (herda estilo). Limpa "ativada" herdada no li E no a.
    const novaAba = abaModelo.cloneNode(true);
    novaAba.id = ABA_ID;
    novaAba.classList.remove(CLASSE_ATIVA);
    novaAba.removeAttribute("onclick");
    const link = novaAba.querySelector("a");
    if (link) {
      link.classList.remove(CLASSE_ATIVA);
      link.id = "def.tab.custom_epi";
      link.setAttribute("name", "def.tab.custom_epi");
      link.setAttribute("title", "Formulário EPIs");
      link.setAttribute("href", "javascript:;");
      link.removeAttribute("onclick");
      link.childNodes.forEach(n => { if (n.nodeType === 3) n.textContent = ""; });
      link.appendChild(doc.createTextNode(" Formulário EPIs "));
    }
    barra.appendChild(novaAba);

    // Container de conteúdo
    const algumConteudo = doc.querySelector(".tabVisivel, .tabOculta");
    if (!algumConteudo) { console.error("[EPI] Não achei .tabOculta/.tabVisivel."); return; }
    const containerConteudo = algumConteudo.parentNode;

    const painel = doc.createElement("div");
    painel.id = ROOT_ID;
    painel.className = "tabOculta";
    painel.innerHTML = montarHtmlFormulario();
    containerConteudo.appendChild(painel);

    // Reforço: aplica estilo essencial inline nos controles, garantindo que
    // apareçam mesmo se o CSS do LOIQ tentar zerá-los com !important.
    painel.querySelectorAll('input[type="text"], input[type="number"], select').forEach(el => {
      el.style.setProperty("display", "block", "important");
      el.style.setProperty("width", "100%", "important");
      el.style.setProperty("min-height", "34px", "important");
      el.style.setProperty("box-sizing", "border-box", "important");
      el.style.setProperty("padding", "6px 8px", "important");
      el.style.setProperty("border", "1px solid #d1d5db", "important");
      el.style.setProperty("border-radius", "6px", "important");
      el.style.setProperty("background-color", el.disabled || el.readOnly ? "#f3f4f6" : "#fff", "important");
      el.style.setProperty("color", "#111827", "important");
      el.style.setProperty("font-size", "0.875rem", "important");
      el.style.setProperty("opacity", "1", "important");
      el.style.setProperty("visibility", "visible", "important");
      const ap = el.tagName === "SELECT" ? "menulist" : "auto";
      el.style.setProperty("-webkit-appearance", ap, "important");
      el.style.setProperty("appearance", ap, "important");
    });

    // ---- Troca de aba (destaque + tabOculta/tabVisivel) ----
    const limparTodas = () =>
      barra.querySelectorAll("." + CLASSE_ATIVA).forEach(el => el.classList.remove(CLASSE_ATIVA));

    const ativarMinha = (e) => {
      if (e) e.preventDefault();
      limparTodas();
      novaAba.classList.add(CLASSE_ATIVA);
      link && link.classList.add(CLASSE_ATIVA);
      doc.querySelectorAll(".tabVisivel").forEach(el => {
        el.classList.remove("tabVisivel"); el.classList.add("tabOculta");
      });
      painel.classList.remove("tabOculta"); painel.classList.add("tabVisivel");
      pendenteTermo = true;
      if (ultimaFicha) {
        talvezMostrarTermo(ultimaFicha);
        if (ultimaFicha.termo_aceito) carregarAvisos(ultimaFicha.num_bm);
      } else consultarFicha();
    };
    novaAba.addEventListener("click", ativarMinha);
    link && link.addEventListener("click", ativarMinha);

    // Ao clicar em aba nativa: remove destaque da minha e oculta o painel.
    [...barra.children].forEach(li => {
      if (li === novaAba) return;
      li.addEventListener("click", () => {
        novaAba.classList.remove(CLASSE_ATIVA);
        link && link.classList.remove(CLASSE_ATIVA);
        painel.classList.remove("tabVisivel"); painel.classList.add("tabOculta");
      }, true); // captura: roda antes do handler nativo
    });

    // ---- Bindings do formulário ----
    const $ = (sel) => painel.querySelector(sel);
    const $$ = (sel) => painel.querySelectorAll(sel);

    function status(msg, isErr) {
      const s = $("#epi-status");
      if (!s) return;
      s.textContent = msg || "";
      s.style.color = isErr ? "#dc2626" : "#16a34a";
    }

    let mostrarErro;
    const errModalOverlay = $("#epi-modal-overlay");
    if (doc.body && errModalOverlay) doc.body.appendChild(errModalOverlay);
    const termoOverlay = $("#epi-termo-overlay");
    if (doc.body && termoOverlay) doc.body.appendChild(termoOverlay);
    const confirmOverlay = $("#epi-confirm-overlay");
    if (doc.body && confirmOverlay) doc.body.appendChild(confirmOverlay);
    let modalTimer = null;
    const _fecharModal = () => {
      if (modalTimer) { clearTimeout(modalTimer); modalTimer = null; }
      if (errModalOverlay) errModalOverlay.style.display = "none";
    };
    function mostrarSucesso(detalhe) {
      mostrarAviso("Dados enviados com sucesso",
        "<p style=\"margin:0;\">Dados enviados com sucesso.</p>"
        + (detalhe ? "<p style=\"margin:8px 0 0;font-size:.85rem;color:#4b5563;\">" + detalhe + "</p>" : ""),
        false);
      modalTimer = setTimeout(_fecharModal, 5000);
    }
    function mostrarAviso(titulo, corpoHtml, isErr) {
      if (modalTimer) { clearTimeout(modalTimer); modalTimer = null; }
      if (!errModalOverlay) {
        status(String(corpoHtml).replace(/<[^>]+>/g, " "), !!isErr);
        return;
      }
      const titleEl = errModalOverlay.querySelector("#epi-modal-title");
      const bodyEl = errModalOverlay.querySelector("#epi-modal-body");
      const okEl = errModalOverlay.querySelector("#epi-modal-ok");
      if (titleEl) {
        titleEl.textContent = titulo;
        titleEl.style.color = isErr ? "#b91c1c" : "#166534";
      }
      if (bodyEl) bodyEl.innerHTML = corpoHtml;
      if (okEl) okEl.style.background = isErr ? "#b71c1c" : "#15803d";
      errModalOverlay.style.setProperty("display", "flex", "important");
      errModalOverlay.style.setProperty("position", "fixed", "important");
      errModalOverlay.style.setProperty("top", "0", "important");
      errModalOverlay.style.setProperty("right", "0", "important");
      errModalOverlay.style.setProperty("bottom", "0", "important");
      errModalOverlay.style.setProperty("left", "0", "important");
      errModalOverlay.style.setProperty("z-index", "2147483647", "important");
      errModalOverlay.style.setProperty("align-items", "center", "important");
      errModalOverlay.style.setProperty("justify-content", "center", "important");
    }

    const termoCheck = termoOverlay?.querySelector("#epi-termo-check");
    const termoBox = termoOverlay?.querySelector(".epi-termo-box");
    const termoOk = termoOverlay?.querySelector("#epi-termo-ok");
    let termoNumBm = "";
    let termoMarcado = false;

    function setTermoMarcado(on) {
      termoMarcado = !!on;
      if (termoCheck) termoCheck.setAttribute("aria-checked", termoMarcado ? "true" : "false");
      if (termoBox) {
        termoBox.textContent = termoMarcado ? "\u2713" : "";
        termoBox.style.background = termoMarcado ? "#b71c1c" : "#fff";
      }
      if (termoOk) {
        termoOk.style.background = termoMarcado ? "#b71c1c" : "#9ca3af";
        termoOk.style.cursor = termoMarcado ? "pointer" : "not-allowed";
        termoOk.style.opacity = termoMarcado ? "1" : "0.85";
      }
    }

    function mostrarTermo(numBm) {
      if (!termoOverlay) return;
      termoNumBm = numBm || "";
      setTermoMarcado(false);
      termoOverlay.style.setProperty("display", "flex", "important");
      termoOverlay.style.setProperty("position", "fixed", "important");
      termoOverlay.style.setProperty("top", "0", "important");
      termoOverlay.style.setProperty("right", "0", "important");
      termoOverlay.style.setProperty("bottom", "0", "important");
      termoOverlay.style.setProperty("left", "0", "important");
      termoOverlay.style.setProperty("z-index", "2147483646", "important");
      termoOverlay.style.setProperty("pointer-events", "auto", "important");
    }

    function fecharTermo() {
      if (termoOverlay) termoOverlay.style.display = "none";
      pendenteTermo = false;
    }

    function aceitarTermo() {
      if (!termoMarcado) return;
      chrome.runtime.sendMessage({ type: "epi-termo", q: termoNumBm }, (resp) => {
        if (chrome.runtime.lastError || !resp || !resp.ok) {
          status((resp && resp.error) || "Não foi possível registrar o termo.", true);
          return;
        }
        fecharTermo();
        if (ultimaFicha) ultimaFicha.termo_aceito = true;
        status("Termo aceito. Pode preencher o formulário.");
        carregarAvisos(termoNumBm || (ultimaFicha && ultimaFicha.num_bm));
      });
    }

    function onTermoPointer(e) {
      if (!termoOverlay || termoOverlay.style.display === "none") return;
      const t = e.target && (e.target.nodeType === 1 ? e.target : e.target.parentElement);
      if (!t || !termoOverlay.contains(t)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      if (e.type !== "click") return;
      if (termoCheck && (t === termoCheck || termoCheck.contains(t))) {
        setTermoMarcado(!termoMarcado);
        return;
      }
      if (termoOk && (t === termoOk || termoOk.contains(t))) aceitarTermo();
    }

    ["pointerdown", "mousedown", "mouseup", "pointerup", "click"].forEach(function (ev) {
      doc.addEventListener(ev, onTermoPointer, true);
      if (termoOverlay) termoOverlay.addEventListener(ev, onTermoPointer, true);
    });

    let avisoNumBm = "";
    let avisosGrupo = {};

    function hostAviso(campo) {
      const m = /^epi\.([^.]+)\./.exec(campo || "");
      if (m) {
        const card = $('[data-card="' + m[1] + '"]');
        if (card) return { gk: "epi." + m[1], label: card.querySelector("h4"), box: card };
      }
      const dg = campo ? $('[data-dg="' + campo + '"]') : null;
      if (dg && dg.parentElement) {
        return { gk: campo, label: dg.parentElement.firstElementChild, box: dg.parentElement };
      }
      const geral = $("#epi-avisos-gerais");
      return { gk: "_geral", label: geral, box: geral };
    }

    function renderGrupoAviso(gk) {
      const g = avisosGrupo[gk];
      if (!g) return;
      if (g.badge) g.badge.remove();
      if (g.painel) g.painel.remove();
      const geral = gk === "_geral" ? $("#epi-avisos-gerais") : null;
      if (!g.itens.length) {
        delete avisosGrupo[gk];
        if (geral) geral.style.display = "none";
        return;
      }
      if (geral) geral.style.display = "block";
      const temRej = g.itens.some(a => a.tipo === "rejeicao");
      const badge = doc.createElement("span");
      badge.className = "epi-aviso-badge";
      badge.dataset.grupo = gk;
      badge.setAttribute("role", "button");
      badge.tabIndex = 0;
      badge.title = "Ver avisos";
      badge.textContent = String(g.itens.length);
      badge.style.cssText = "display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;"
        + "padding:0 6px;margin-left:8px;border-radius:10px;font-size:11px;font-weight:700;color:#fff;cursor:pointer;"
        + "user-select:none;text-transform:none;letter-spacing:0;vertical-align:middle;"
        + "background:" + (temRej ? "#dc2626" : "#16a34a") + ";";
      if (g.label) g.label.appendChild(badge);

      const painelAv = doc.createElement("div");
      painelAv.className = "epi-aviso-painel";
      painelAv.style.cssText = "margin-top:10px;display:" + (g.aberto ? "flex" : "none") + ";flex-direction:column;gap:8px;";
      g.itens.forEach(a => {
        const rej = a.tipo === "rejeicao";
        const item = doc.createElement("div");
        item.style.cssText = "padding:10px 12px;border-radius:6px;font-size:.85rem;line-height:1.45;display:flex;gap:12px;"
          + "align-items:flex-start;justify-content:space-between;text-transform:none;letter-spacing:0;font-weight:400;"
          + (rej ? "background:#fef2f2;border:1px solid #fca5a5;color:#7f1d1d;"
                 : "background:#f0fdf4;border:1px solid #86efac;color:#14532d;");
        const txt = doc.createElement("div");
        const tit = doc.createElement("strong");
        tit.textContent = rej ? "Solicitação rejeitada" : "Solicitação aprovada";
        tit.style.display = "block";
        const msg = doc.createElement("span");
        msg.textContent = a.mensagem || "";
        txt.appendChild(tit);
        txt.appendChild(msg);
        const ok = doc.createElement("span");
        ok.className = "epi-aviso-okinline";
        ok.dataset.id = String(a.id);
        ok.dataset.grupo = gk;
        ok.setAttribute("role", "button");
        ok.tabIndex = 0;
        ok.textContent = "OK";
        ok.style.cssText = "padding:4px 14px;border-radius:6px;color:#fff;font-weight:600;cursor:pointer;user-select:none;flex-shrink:0;"
          + "background:" + (rej ? "#b71c1c" : "#15803d") + ";";
        item.appendChild(txt);
        item.appendChild(ok);
        painelAv.appendChild(item);
      });
      if (g.box) g.box.appendChild(painelAv);
      g.badge = badge;
      g.painel = painelAv;
    }

    function marcarAvisoLido(gk, id) {
      chrome.runtime.sendMessage({ type: "epi-aviso-lida", q: avisoNumBm, id: id }, (resp) => {
        if (chrome.runtime.lastError || !resp || !resp.ok) {
          status((resp && resp.error) || "Não foi possível marcar o aviso como lido.", true);
          return;
        }
        const g = avisosGrupo[gk];
        if (!g) return;
        g.itens = g.itens.filter(a => a.id !== id);
        renderGrupoAviso(gk);
      });
    }

    function onAvisoInline(e) {
      const t = e.target && (e.target.nodeType === 1 ? e.target : e.target.parentElement);
      if (!t || typeof t.closest !== "function" || !painel.contains(t)) return;
      const badge = t.closest(".epi-aviso-badge");
      const ok = t.closest(".epi-aviso-okinline");
      if (!badge && !ok) return;
      if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      if (badge) {
        const g = avisosGrupo[badge.dataset.grupo];
        if (!g || !g.painel) return;
        g.aberto = !g.aberto;
        g.painel.style.display = g.aberto ? "flex" : "none";
      } else {
        marcarAvisoLido(ok.dataset.grupo, Number(ok.dataset.id));
      }
    }
    ["click", "keydown"].forEach(ev => doc.addEventListener(ev, onAvisoInline, true));

    function carregarAvisos(numBm) {
      const q = numBm || (ultimaFicha && ultimaFicha.num_bm) || "";
      if (!q) return;
      chrome.runtime.sendMessage({ type: "epi-avisos", q: q }, (resp) => {
        if (chrome.runtime.lastError || !resp || !resp.ok) return;
        const lista = (resp.data && resp.data.avisos) || [];
        avisoNumBm = q;
        Object.keys(avisosGrupo).forEach(gk => {
          avisosGrupo[gk].itens = [];
          renderGrupoAviso(gk);
        });
        avisosGrupo = {};
        lista.forEach(a => {
          const h = hostAviso(a.campo);
          if (!avisosGrupo[h.gk]) avisosGrupo[h.gk] = { label: h.label, box: h.box, itens: [], aberto: false };
          avisosGrupo[h.gk].itens.push(a);
        });
        Object.keys(avisosGrupo).forEach(renderGrupoAviso);
      });
    }

    mostrarErro = function (campos) {
      mostrarAviso(
        "Campos obrigatórios",
        '<p style="margin:0 0 8px;">Os campos a seguir devem ser preenchidos:</p>'
        + '<ul style="margin:0;padding-left:20px;">' + campos.map(c => "<li>" + c + "</li>").join("") + "</ul>",
        true
      );
    };

    function possuiChange(sel, key) {
      const cons = painel.querySelector('[data-item="' + key + '"][data-attr="conservacao"]');
      if (cons) {
        if (sel.value === "POSSUI") { cons.disabled = false; }
        else { cons.value = ""; cons.disabled = true; }
      }

      const justBox = painel.querySelector('.epi-justificativa-box[data-item="' + key + '"]');
      if (justBox) {
        let eraPossui = false;
        if (baseline && Array.isArray(baseline.itens)) {
          const baseItem = baseline.itens.find(i => i.item_key === key);
          eraPossui = ((baseItem && baseItem.possui) || "").trim() === "POSSUI";
        }
        const mudouParaNaoPossui = eraPossui && sel.value === "NÃO POSSUI";
        if (mudouParaNaoPossui) {
          justBox.style.display = "block";
          const txt = justBox.querySelector('textarea');
          if (txt && !txt.value.trim()) txt.focus();
        } else {
          justBox.style.display = "none";
        }
      }
    }
    $$('[data-attr="possui"]').forEach(sel => {
      sel.addEventListener("change", () => possuiChange(sel, sel.dataset.item));
    });

    function lerControle(el) {
      if (!el) return "";
      if (el.tagName === "SELECT") {
        const i = el.selectedIndex;
        const opt = i >= 0 ? el.options[i] : null;
        return String(el.value || (opt && opt.value) || "").trim();
      }
      return String(el.value || "").trim();
    }

    function coletar() {
      const p = { itens: [] };
      DADOS_GERAIS.forEach(f => {
        const v = lerControle($('[data-dg="' + f.key + '"]'));
        p[f.key] = FLOAT_KEYS.has(f.key) ? (v === "" ? null : Number(v.replace(",", "."))) : v;
      });
      READONLY.forEach(f => { const el = $('[data-ro="' + f.key + '"]'); if (el) p[f.key] = el.value.trim(); });
      GRUPOS.forEach(g => g.itens.forEach(item => {
        const get = (a) => $('[data-item="' + item.key + '"][data-attr="' + a + '"]')?.value.trim() || "";
        p.itens.push({
          item_key: item.key,
          possui: get("possui"),
          cor: get("cor"),
          conservacao: get("conservacao"),
          justificativa: get("justificativa")
        });
      }));
      return p;
    }

    function validar(p) {
      const faltando = [];
      DADOS_GERAIS.forEach(f => {
        const v = p[f.key];
        if (v === null || v === undefined || String(v).trim() === "") faltando.push(f.label);
      });
      const baseItens = Object.fromEntries(((baseline && baseline.itens) || []).map(i => [i.item_key, i]));
      p.itens.forEach(it => {
        if (it.possui === "POSSUI" && !it.conservacao) {
          faltando.push("Estado de conservação de '" + ITEM_LABEL[it.item_key] + "'");
        }
        const b = baseItens[it.item_key] || {};
        const posseCritica = (b.possui || "").trim() === "POSSUI"
          && (it.possui || "").trim() === "NÃO POSSUI";
        if (posseCritica && !(it.justificativa || "").trim()) {
          faltando.push("Justificativa de alteração de posse para 'NÃO POSSUI' em '" + ITEM_LABEL[it.item_key] + "'");
        }
      });
      return faltando;
    }

    let baseline = null;
    let enviando = false;

    function fichaParaBaseline(d) {
      const p = { itens: [] };
      DADOS_GERAIS.forEach(f => { p[f.key] = d ? d[f.key] : null; });
      if (d && Array.isArray(d.itens)) {
        p.itens = d.itens.map(i => ({
          item_key: i.item_key,
          possui: i.possui || "",
          cor: i.cor || "",
          conservacao: i.conservacao || ""
        }));
      }
      if (d && d.num_bm) p.num_bm = d.num_bm;
      return p;
    }

    function normCampo(key, v) {
      if (v == null) return "";
      const s = String(v).trim();
      if (FLOAT_KEYS.has(key) && s !== "") {
        const n = Number(s.replace(",", "."));
        if (!isNaN(n)) return n === Math.trunc(n) ? String(Math.trunc(n)) : String(n);
      }
      return s;
    }

    function montarAlteracoes(atual, base) {
      const alteracoes = [];
      const origem = base || {};
      DADOS_GERAIS.forEach(f => {
        const novo = normCampo(f.key, atual[f.key]);
        const antigo = normCampo(f.key, origem[f.key]);
        if (novo !== antigo) {
          alteracoes.push({
            campo: f.key,
            valor_novo: atual[f.key] == null ? "" : String(atual[f.key]).trim()
          });
        }
      });
      const baseItens = Object.fromEntries((origem.itens || []).map(i => [i.item_key, i]));
      (atual.itens || []).forEach(it => {
        const b = baseItens[it.item_key] || {};
        const posseCritica = (b.possui || "").trim() === "POSSUI"
          && (it.possui || "").trim() === "NÃO POSSUI";
        ["possui", "cor", "conservacao"].forEach(attr => {
          if (posseCritica && attr !== "possui") return;
          const novo = (it[attr] || "").trim();
          const antigo = (b[attr] || "").trim();
          if (novo !== antigo) {
            const alt = {
              campo: "epi." + it.item_key + "." + attr,
              valor_novo: novo
            };
            if (attr === "possui" && posseCritica) {
              alt.justificativa = (it.justificativa || "").trim();
            }
            alteracoes.push(alt);
          }
        });
      });
      return alteracoes;
    }

    const ATTR_LABEL = { possui: "Possui?", cor: "Cor", conservacao: "Estado de conservação" };
    const SEL_EDITAVEIS = '[data-dg], [data-item][data-attr="possui"], [data-item][data-attr="cor"], [data-item][data-attr="conservacao"]';

    function chaveCampo(el) {
      return el.dataset.dg || el.dataset.item;
    }

    function textoValor(el, v) {
      if (v === "") return "(vazio)";
      if (el.tagName === "SELECT") {
        const o = [...el.options].find(op => op.value === v);
        if (o) return o.textContent.trim();
      }
      return v;
    }

    function esc(s) {
      return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    }

    function campoMudou(el) {
      if (el.dataset.orig === undefined) return false;
      const k = chaveCampo(el);
      return normCampo(k, lerControle(el)) !== normCampo(k, el.dataset.orig);
    }

    function pintarCampo(el) {
      if (campoMudou(el)) {
        el.style.setProperty("background-color", "#fef9c3", "important");
        el.style.setProperty("border", "1px solid #f97316", "important");
        el.style.setProperty("box-shadow", "0 0 0 1px #f97316", "important");
      } else {
        el.style.setProperty("background-color", el.disabled || el.readOnly ? "#f3f4f6" : "#fff", "important");
        el.style.setProperty("border", "1px solid #d1d5db", "important");
        el.style.setProperty("box-shadow", "none", "important");
      }
    }

    function atualizarDestaques() {
      $$(SEL_EDITAVEIS).forEach(pintarCampo);
    }

    function guardarOriginais() {
      $$(SEL_EDITAVEIS).forEach(el => { el.dataset.orig = lerControle(el); });
      atualizarDestaques();
    }

    ["input", "change"].forEach(ev => painel.addEventListener(ev, (e) => {
      if (e.target && e.target.matches && e.target.matches(SEL_EDITAVEIS)) setTimeout(atualizarDestaques, 0);
    }, true));

    function listarMudancas() {
      const lista = [];
      $$(SEL_EDITAVEIS).forEach(el => {
        if (!campoMudou(el)) return;
        const rotulo = el.dataset.dg
          ? DG_LABEL[el.dataset.dg]
          : ITEM_LABEL[el.dataset.item] + " — " + ATTR_LABEL[el.dataset.attr];
        const m = { rotulo: rotulo, antes: textoValor(el, el.dataset.orig), depois: textoValor(el, lerControle(el)) };
        if (el.dataset.attr === "possui") {
          const j = $('[data-item="' + el.dataset.item + '"][data-attr="justificativa"]');
          if (j && j.value.trim()) m.justificativa = j.value.trim();
        }
        lista.push(m);
      });
      return lista;
    }

    let acaoConfirmar = null;
    function fecharConfirmacao() {
      acaoConfirmar = null;
      if (confirmOverlay) confirmOverlay.style.display = "none";
    }
    function abrirConfirmacao(mudancas, onOk) {
      if (!confirmOverlay) { onOk(); return; }
      acaoConfirmar = onOk;
      const body = confirmOverlay.querySelector("#epi-confirm-body");
      if (body) {
        body.innerHTML = '<ul style="margin:0;padding-left:20px;">' + mudancas.map(m =>
          '<li style="margin-bottom:6px;"><strong>' + esc(m.rotulo) + '</strong>: '
          + '<span style="color:#6b7280;">' + esc(m.antes) + '</span> &rarr; '
          + '<span style="color:#c2410c;font-weight:600;">' + esc(m.depois) + '</span>'
          + (m.justificativa ? '<br><span style="font-size:.85rem;color:#4b5563;">Justificativa: ' + esc(m.justificativa) + '</span>' : '')
          + '</li>').join("") + '</ul>';
      }
      ["display:flex", "position:fixed", "top:0", "right:0", "bottom:0", "left:0", "z-index:2147483647",
        "align-items:center", "justify-content:center"].forEach(p => {
        const i = p.indexOf(":");
        confirmOverlay.style.setProperty(p.slice(0, i), p.slice(i + 1), "important");
      });
    }

    function onConfirmEvent(e) {
      if (!confirmOverlay || confirmOverlay.style.display === "none") return;
      const t = e.target && (e.target.nodeType === 1 ? e.target : e.target.parentElement);
      if (!t || !confirmOverlay.contains(t)) return;
      if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      if (e.type !== "click" && e.type !== "keydown") return;
      const ok = confirmOverlay.querySelector("#epi-confirm-ok");
      const cancelar = confirmOverlay.querySelector("#epi-confirm-cancelar");
      if (ok && (t === ok || ok.contains(t))) {
        const acao = acaoConfirmar;
        fecharConfirmacao();
        if (acao) acao();
      } else if (t === confirmOverlay || (cancelar && (t === cancelar || cancelar.contains(t)))) {
        fecharConfirmacao();
        status("Envio cancelado.", true);
      }
    }
    ["pointerdown", "mousedown", "mouseup", "pointerup", "click", "keydown"].forEach(ev => {
      doc.addEventListener(ev, onConfirmEvent, true);
      if (confirmOverlay) confirmOverlay.addEventListener(ev, onConfirmEvent, true);
    });

    function enviar() {
      if (enviando) return;
      let p;
      try { p = coletar(); }
      catch (err) {
        console.error("[EPI] coletar:", err);
        mostrarAviso("Falha ao enviar", "<p>Não foi possível ler o formulário.</p>", true);
        return;
      }
      const faltando = validar(p);
      if (faltando.length) { mostrarErro(faltando); return; }
      const numBm = (ultimaFicha && ultimaFicha.num_bm) || p.num_bm;
      if (!numBm) {
        status("Aguarde o carregamento da ficha antes de enviar.", true);
        mostrarAviso("Aguarde", "<p>Aguarde o carregamento da ficha antes de enviar.</p>", true);
        return;
      }
      const mudancas = listarMudancas();
      if (!mudancas.length) {
        status("Nenhum campo foi alterado.", true);
        mostrarAviso("Nenhuma alteração", "<p>Nenhum campo foi alterado. Nada foi enviado.</p>", true);
        return;
      }
      abrirConfirmacao(mudancas, () => enviarPayload(p, numBm));
    }

    function enviarPayload(p, numBm) {
      if (enviando) return;
      const alteracoes = montarAlteracoes(p, baseline);
      enviando = true;
      status("Enviando…");
      const payload = Object.assign({}, p, {
        num_bm: numBm,
        solicitado_por: numBm,
        alteracoes: alteracoes
      });
      console.log("[EPI] enviando", payload);
      let respondido = false;
      const timer = setTimeout(() => {
        if (respondido) return;
        enviando = false;
        status("A API não respondeu. Verifique se está em localhost:8000.", true);
        mostrarAviso("Falha ao enviar",
          "<p>A API não respondeu em 15 segundos. Confira se está rodando em <code>http://localhost:8000</code>.</p>",
          true);
      }, 15000);
      chrome.runtime.sendMessage({ type: "epi-salvar", payload: payload }, (resp) => {
        if (respondido) return;
        respondido = true;
        clearTimeout(timer);
        enviando = false;
        if (chrome.runtime.lastError || !resp || !resp.ok) {
          const err = (resp && resp.error) || (chrome.runtime.lastError && chrome.runtime.lastError.message) || "Falha ao enviar.";
          status(err, true);
          mostrarAviso("Falha ao enviar", "<p>" + err + "</p>", true);
          return;
        }
        const d = resp.data || {};
        if (d.status === "sem_alteracao") {
          status("Nenhuma alteração em relação ao banco.", false);
          mostrarAviso("Nada a gravar", "<p>Nenhuma alteração em relação ao banco.</p>", false);
        } else {
          const detalhe = d.status === "pendente"
            ? "Alteração de posse enviada para aprovação do administrador."
            : "";
          status("Dados enviados com sucesso.", false);
          mostrarSucesso(detalhe);
        }
        baseline = coletar();
        guardarOriginais();
        console.log("[EPI] envio:", d);
      });
    }

    function alvoEnviar(t) {
      if (!t) return null;
      if (t.id === "epi-enviar") return t;
      if (typeof t.closest === "function") return t.closest("#epi-enviar");
      return null;
    }
    function onEnviarEvent(e) {
      const btn = alvoEnviar(e.target);
      if (!btn) return;
      if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      if (e.type === "click" || e.type === "keydown") enviar();
    }
    ["click", "keydown"].forEach(ev => {
      doc.addEventListener(ev, onEnviarEvent, true);
      painel.addEventListener(ev, onEnviarEvent, true);
    });

    function onModalOkEvent(e) {
      if (!errModalOverlay || errModalOverlay.style.display === "none") return;
      const t = e.target && (e.target.nodeType === 1 ? e.target : e.target.parentElement);
      if (!t) return;
      const ok = errModalOverlay.querySelector("#epi-modal-ok");
      const clicouOk = ok && (t === ok || (ok.contains && ok.contains(t)));
      const clicouFundo = t === errModalOverlay;
      if (!clicouOk && !clicouFundo) return;
      if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      if (e.type === "click" || e.type === "keydown") _fecharModal();
    }
    ["click", "keydown"].forEach(ev => doc.addEventListener(ev, onModalOkEvent, true));

    function setField(el, value) {
      if (!el) return;
      const vazio = value == null || String(value).trim() === "" || String(value).trim().toLowerCase() === "none";
      if (vazio) {
        el.value = "";
        return;
      }
      let raw = String(value).trim();

      if (el.tagName === "SELECT") {
        if (el.dataset.ro === "posto_grad") raw = mapPostoGrad(raw) || raw;
        const nk = normTxt(raw);
        let match = [...el.options].find(o =>
          o.value === raw || normTxt(o.value) === nk || normTxt(o.textContent) === nk);
        if (!match && raw !== "" && !isNaN(Number(String(raw).replace(",", ".")))) {
          const n = String(parseInt(Number(String(raw).replace(",", ".")), 10));
          match = [...el.options].find(o => o.value === n);
        }
        if (!match) {
          const opt = doc.createElement("option");
          opt.value = raw;
          opt.textContent = String(value).trim();
          el.appendChild(opt);
          el.value = raw;
        } else {
          el.value = match.value;
        }
        return;
      }

      if (el.type === "number") {
        const num = Number(String(raw).replace(",", "."));
        if (!isNaN(num)) el.value = String(num);
        return;
      }
      el.value = raw;
    }

    function popularFormulario(d) {
      if (!d) return;
      baseline = fichaParaBaseline(d);
      ultimaFicha = d;
      setField($('[data-ro="num_bm"]'), d.num_bm);
      setField($('[data-ro="posto_grad"]'), d.posto_grad);
      setField($('[data-ro="descricao_quadro"]'), d.descricao || d.descricao_quadro);
      setField($('[data-ro="nome_completo"]'), d.nome_completo);
      setField($('[data-ro="ativo_inativo"]'), d.ativo_inativo);
      setField($('[data-ro="situacao_funcional"]'), d.situacao_funcional);
      setField($('[data-ro="unidade_principal"]'), d.unidade_principal);
      setField($('[data-ro="unidade_lotacao"]'), d.unidade_lotacao);

      DADOS_GERAIS.forEach(f => {
        const sel = SEL_MAO[f.key];
        let el = sel ? doc.querySelector(sel) : null;
        if (el && el.dataset.dg !== f.key) {
          console.warn("[EPI] seletor de " + f.key + " aponta para outro campo; usando data-dg.");
          el = null;
        }
        setField(el || $('[data-dg="' + f.key + '"]'), d[f.key]);
      });

      const itens = Array.isArray(d.itens) ? d.itens : [];
      const byKey = Object.fromEntries(itens.map(i => [i.item_key, i]));
      GRUPOS.forEach(g => g.itens.forEach(item => {
        const it = byKey[item.key] || {};
        setField($('[data-item="' + item.key + '"][data-attr="possui"]'), it.possui);
        setField($('[data-item="' + item.key + '"][data-attr="cor"]'), it.cor);
        const pe = $('[data-item="' + item.key + '"][data-attr="possui"]');
        if (pe) possuiChange(pe, item.key);
        setField($('[data-item="' + item.key + '"][data-attr="conservacao"]'), it.conservacao);
        const txtJ = $('[data-item="' + item.key + '"][data-attr="justificativa"]');
        if (txtJ) txtJ.value = "";
      }));
      guardarOriginais();
    }

    let consultaEmAndamento = false;
    let ultimaFicha = null;
    let pendenteTermo = false;

    function talvezMostrarTermo(d, numero) {
      if (!d || d.termo_aceito) { pendenteTermo = false; return; }
      if (!painel.classList.contains("tabVisivel")) return;
      if (!pendenteTermo) return;
      mostrarTermo(d.num_bm || numero || "");
      pendenteTermo = false;
    }

    function consultarFicha(tentativa) {
      const t = tentativa || 0;
      const numero = extrairNumeroAmplo(doc);
      if (!numero) {
        if (t < 8) {
          setTimeout(() => consultarFicha(t + 1), 400);
          return;
        }
        status("Não achei o número na ficha.", true);
        console.warn("[EPI] seletor do número não encontrou valor.");
        return;
      }
      if (consultaEmAndamento) return;
      consultaEmAndamento = true;
      status("Consultando " + numero + "…");
      console.log("[EPI] consulta API q=", numero);
      chrome.runtime.sendMessage({ type: "epi-consulta", q: numero }, (resp) => {
        consultaEmAndamento = false;
        if (chrome.runtime.lastError) {
          status("Falha na extensão: " + chrome.runtime.lastError.message, true);
          return;
        }
        if (!resp || !resp.ok) {
          status(resp && resp.error ? resp.error : "API indisponível em localhost:8000.", true);
          return;
        }
        const d = resp.data;
        if (!d || d.detail || !d.nome_completo) {
          status("Militar não encontrado para " + numero + ".", true);
          return;
        }
        popularFormulario(d);
        ultimaFicha = d;
        baseline = fichaParaBaseline(d);
        status("Dados carregados: " + d.nome_completo);
        console.log("[EPI] ficha preenchida:", d);
        talvezMostrarTermo(d, numero);
        if (d.termo_aceito) carregarAvisos(d.num_bm || numero);
      });
    }

    // Popular programaticamente, se desejado
    window.cbmmgEpiPopular = function (data) {
      if (!data) return;
      popularFormulario(data);
      ultimaFicha = data;
      baseline = fichaParaBaseline(data);
      status("Dados carregados.");
    };

    console.log('✅ [EPI] Aba "Formulário EPIs" injetada.');
    consultarFicha();
  }

  // ---- Boot + observer ------------------------------------------------------
  function tentarInjetar() {
    if (temAADP(document)) injetar(document);
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", tentarInjetar);
  else
    tentarInjetar();

  // A página é dinâmica: reobserva para reinjetar se o DOM recriar as abas.
  let busy = false;
  const obs = new MutationObserver(() => {
    if (busy || !document.body) return;
    busy = true;
    obs.disconnect();
    try { tentarInjetar(); }
    finally {
      if (document.body) obs.observe(document.body, { childList: true, subtree: true });
      busy = false;
    }
  });
  function startObs() {
    if (document.body) obs.observe(document.body, { childList: true, subtree: true });
  }
  if (document.body) startObs();
  else document.addEventListener("DOMContentLoaded", startObs);
})();