/* Consulta e envio para a API local (service worker, sem CORS da página). */
const API_BASE = "http://localhost:8000";

function jsonFetch(url, opts, sendResponse) {
  fetch(url, opts)
    .then(async (r) => {
      let data = null;
      try { data = await r.json(); } catch (_) { data = null; }
      if (!r.ok) {
        const detail = data && (data.detail || data.message);
        const msgErr = typeof detail === "string" ? detail
          : (detail && detail.message) || ("HTTP " + r.status);
        sendResponse({ ok: false, error: msgErr, data: data });
        return;
      }
      sendResponse({ ok: true, data: data });
    })
    .catch((e) => {
      sendResponse({
        ok: false,
        error: "API indisponível em " + API_BASE + " (" + (e && e.message ? e.message : e) + ")"
      });
    });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || !msg.type) return;

  if (msg.type === "epi-salvar") {
    jsonFetch(API_BASE + "/api/alteracoes", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(msg.payload || {}),
    }, sendResponse);
    return true;
  }

  if (msg.type === "epi-avisos") {
    const q = String(msg.q || "").replace(/\s+/g, "").trim();
    if (!q) {
      sendResponse({ ok: false, error: "Número vazio" });
      return;
    }
    jsonFetch(
      API_BASE + "/consulta/avisos?q=" + encodeURIComponent(q),
      { headers: { accept: "application/json" } },
      sendResponse
    );
    return true;
  }

  if (msg.type === "epi-aviso-lida") {
    const q = String(msg.q || "").replace(/\s+/g, "").trim();
    const id = msg.id;
    if (!q || !id) {
      sendResponse({ ok: false, error: "Parâmetros inválidos" });
      return;
    }
    jsonFetch(
      API_BASE + "/consulta/avisos/" + encodeURIComponent(id) + "/lida?q=" + encodeURIComponent(q),
      { method: "POST", headers: { accept: "application/json" } },
      sendResponse
    );
    return true;
  }

  if (msg.type !== "epi-consulta" && msg.type !== "epi-termo") return;

  const q = String(msg.q || "").replace(/\s+/g, "").trim();
  if (!q) {
    sendResponse({ ok: false, error: "Número vazio" });
    return;
  }

  const url = msg.type === "epi-termo"
    ? API_BASE + "/consulta/termo?q=" + encodeURIComponent(q)
    : API_BASE + "/consulta?q=" + encodeURIComponent(q);
  const opts = msg.type === "epi-termo"
    ? { method: "POST", headers: { accept: "application/json" } }
    : { headers: { accept: "application/json" } };

  jsonFetch(url, opts, sendResponse);
  return true;
});
