/* Busca Licitações — PWA (vanilla JS, sem build). Rotas por hash (#/...). */
(() => {
  "use strict";

  /* ===================== Constantes ===================== */
  const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");
  const MODALIDADES = {
    pregao: "Pregão", concorrencia: "Concorrência", concurso: "Concurso", leilao: "Leilão",
    dialogo_competitivo: "Diálogo competitivo", dispensa: "Dispensa", inexigibilidade: "Inexigibilidade",
    convite: "Convite", tomada_precos: "Tomada de preços", credenciamento: "Credenciamento",
    pre_qualificacao: "Pré-qualificação", manifestacao_interesse: "Manifestação de interesse", outra: "Outra",
  };
  const STATUS = {
    publicada: "Publicada", aberta: "Aberta", em_julgamento: "Em julgamento", homologada: "Homologada",
    suspensa: "Suspensa", revogada: "Revogada", cancelada: "Cancelada", encerrada: "Encerrada",
  };
  const ORDENACOES = {
    "": "Mais recentes",
    "-valor_estimado": "Maior valor",
    "valor_estimado": "Menor valor",
    "data_encerramento_propostas": "Encerra primeiro",
    "-data_abertura": "Abertura mais recente",
  };
  const ROTULOS = {
    q: "Palavra-chave", uf: "UF", modalidade: "Modalidade", status: "Status", municipio: "Município",
    valor_min: "Valor mín.", valor_max: "Valor máx.", publicacao_de: "Publicado de",
    publicacao_ate: "Publicado até", abertas: "Abertas", palavras: "Palavras", combinar: "Modo",
  };
  const TOKEN_KEY = "bl.tokens";

  /* ===================== Utilidades ===================== */
  class Raw { constructor(s) { this.s = s; } }
  const raw = (s) => new Raw(s);
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
  const val = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(val).join("") : v === false || v == null ? "" : esc(v));
  const html = (strs, ...vals) => new Raw(strs.reduce((a, s, i) => a + s + (i < vals.length ? val(vals[i]) : ""), ""));

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const fmtValor = (v) => (v == null ? "Valor não informado" : brl.format(Number(v)));
  const fmtData = (iso) => {
    if (!iso) return "—";
    const d = iso.length <= 10 ? new Date(iso + "T12:00:00") : new Date(iso);
    return d.toLocaleDateString("pt-BR");
  };
  const fmtDataHora = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    // 23:59 = fonte só informa a data (prazo vale até o fim do dia).
    if (d.getHours() === 23 && d.getMinutes() === 59) return d.toLocaleDateString("pt-BR");
    return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  };
  function prazo(iso) {
    if (!iso) return null;
    const ms = new Date(iso) - Date.now();
    if (ms < 0) return { txt: "Encerrada", cls: "gray" };
    const h = ms / 36e5;
    if (h < 24) return { txt: `Encerra em ${Math.max(1, Math.round(h))}h`, cls: "red" };
    const d = Math.ceil(h / 24);
    return { txt: `Encerra em ${d} dia${d > 1 ? "s" : ""}`, cls: d <= 3 ? "red" : "" };
  }
  const statusCls = (s) => (s === "aberta" || s === "publicada" ? "green" : ["suspensa", "revogada", "cancelada"].includes(s) ? "red" : "gray");

  let toastTimer;
  function toast(msg, erro = false) {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast" + (erro ? " err" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 3200);
  }

  const icons = {
    search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>',
    filter: '<svg viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
    bell: '<svg viewBox="0 0 24 24"><path d="M6 17V11a6 6 0 0112 0v6l1.5 2h-15z"/><path d="M10 21h4"/></svg>',
    plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
    inbox: '<svg viewBox="0 0 24 24"><path d="M4 13l2-8h12l2 8v6H4z"/><path d="M4 13h5l1 2h4l1-2h5"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    ext: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/></svg>',
  };

  /* ===================== Push ===================== */
  const push = {
    suportado: () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window,
    b64ToBytes(b64) {
      const pad = "=".repeat((4 - (b64.length % 4)) % 4);
      const bin = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
      return Uint8Array.from(bin, (c) => c.charCodeAt(0));
    },
    // `ready` nunca resolve se o service worker não registrou (ex.: HTTP fora de
    // localhost): sem o limite de tempo a tela Conta ficaria travada.
    async registro() {
      return Promise.race([
        navigator.serviceWorker.ready,
        new Promise((_, rej) => setTimeout(() => rej(new Error("Service worker indisponível.")), 3000)),
      ]);
    },
    async atual() {
      if (!push.suportado()) return null;
      try { return await (await push.registro()).pushManager.getSubscription(); } catch { return null; }
    },
    async ativar() {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") throw new Error("Permissão negada. Libere as notificações nas configurações do navegador.");
      const { public_key } = await api("/push/public-key/");
      const reg = await push.registro();
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: push.b64ToBytes(public_key) });
      }
      await api("/push/subscriptions/", { method: "POST", body: sub.toJSON() });
    },
    async desativar() {
      const sub = await push.atual();
      if (!sub) return;
      try { await api("/push/subscriptions/", { method: "DELETE", body: { endpoint: sub.endpoint } }); } catch { /* segue */ }
      await sub.unsubscribe();
    },
  };

  /* ===================== Sessão / API ===================== */
  const session = {
    get() { try { return JSON.parse(localStorage.getItem(TOKEN_KEY)) || null; } catch { return null; } },
    set(t) { try { localStorage.setItem(TOKEN_KEY, JSON.stringify(t)); } catch { /* modo privado */ } },
    clear() { try { localStorage.removeItem(TOKEN_KEY); } catch { /* */ } },
  };
  const state = { user: null, installEvent: null, busca: null, naoLidas: 0 };

  class ApiError extends Error {
    constructor(status, data) {
      super(typeof data === "string" ? data : "Erro na requisição");
      this.status = status; this.data = data;
    }
    /** Mensagem amigável a partir do corpo de erro do DRF. */
    get texto() {
      const d = this.data;
      if (!d || typeof d === "string") return d || "Erro inesperado.";
      if (d.detail) return d.detail;
      const partes = [];
      for (const [k, v] of Object.entries(d)) {
        const m = Array.isArray(v) ? v.join(" ") : typeof v === "object" ? JSON.stringify(v) : v;
        partes.push(k === "non_field_errors" ? m : `${k}: ${m}`);
      }
      return partes.join(" • ") || "Erro inesperado.";
    }
  }

  let refreshing = null;
  async function refreshToken() {
    const t = session.get();
    if (!t || !t.refresh) return false;
    refreshing ||= fetch("/api/auth/token/refresh/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: t.refresh }),
    }).then(async (r) => {
      if (!r.ok) return false;
      const d = await r.json();
      session.set({ access: d.access, refresh: d.refresh || t.refresh });
      return true;
    }).catch(() => false).finally(() => { refreshing = null; });
    return refreshing;
  }

  async function api(path, { method = "GET", body, auth = true, _retry = false } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const t = session.get();
    if (auth && t && t.access) headers.Authorization = `Bearer ${t.access}`;
    const r = await fetch("/api" + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
    if (r.status === 401 && auth && !_retry && t && (await refreshToken())) {
      return api(path, { method, body, auth, _retry: true });
    }
    if (r.status === 204) return null;
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) {
      if (r.status === 401 && auth) {
        session.clear(); state.user = null;
        if (!/^#\/(login|cadastro|redefinir-senha)/.test(location.hash)) { state.next = location.hash; location.hash = "#/login"; }
      }
      throw new ApiError(r.status, data);
    }
    return data;
  }

  async function carregarUsuario() {
    if (!session.get()) return null;
    try { state.user = await api("/auth/me/"); } catch { state.user = null; }
    return state.user;
  }

  /* ===================== Filtros (busca e alertas) ===================== */
  const FILTRO_KEYS = ["q", "uf", "modalidade", "status", "municipio", "valor_min", "valor_max", "publicacao_de", "publicacao_ate", "abertas"];
  const limpar = (f) => Object.fromEntries(Object.entries(f || {}).filter(([, v]) => v !== "" && v != null && v !== false));
  const contarFiltros = (f) => Object.keys(limpar(f)).filter((k) => k !== "ordering" && k !== "combinar").length;
  const lista = (v) => (v ? String(v).split(",").filter(Boolean) : []);

  function filtrosHTML(f = {}, { tags = false } = {}) {
    const sel = (k) => new Set(lista(f[k]));
    const grupo = (nome, opts, marcados) => html`<div class="opts">${Object.entries(opts).map(([v, t]) =>
      html`<label class="opt"><input type="checkbox" name="${nome}" value="${v}" ${marcados.has(v) ? raw("checked") : ""}><span>${t}</span></label>`)}</div>`;
    return html`
      <div class="stack">
        ${tags ? html`
          <div class="field"><label>Palavras-chave</label>
            <div class="tags" data-tags data-valor="${f.palavras || ""}">
              <div class="chips tags-lista" data-tags-lista></div>
              <div class="tags-add">
                <input class="input" data-tag-input placeholder="Ex.: notebook ou frase" enterkeyhint="done" maxlength="60" autocapitalize="none">
                <button type="button" class="btn small" data-tag-add>Adicionar</button>
              </div>
              <div class="small muted" data-tags-info></div>
            </div>
            <span class="small muted">Avisa quando a licitação contiver <b>qualquer uma</b> das palavras. Use espaços para frases (ex.: material de limpeza).</span>
          </div>
          ${f.q ? html`<div class="field"><label>Contém todas as palavras</label>
            <input class="input" name="q" value="${f.q}" enterkeyhint="done"></div>` : ""}`
        : html`<div class="field"><label>Palavra-chave</label>
          <input class="input" name="q" value="${f.q || ""}" placeholder="Ex.: notebook, merenda, obra" enterkeyhint="done"></div>`}
        <fieldset class="modo">
          <legend>Como combinar os critérios</legend>
          <label class="modo-op"><input type="radio" name="combinar" value="todos" ${f.combinar === "qualquer" ? "" : raw("checked")}>
            <span><b>Restringir</b><small>precisa atender a <u>todos</u> os filtros (palavra-chave <u>e</u> modalidade)</small></span></label>
          <label class="modo-op"><input type="radio" name="combinar" value="qualquer" ${f.combinar === "qualquer" ? raw("checked") : ""}>
            <span><b>Somar</b><small>aparece se casar com <u>qualquer</u> palavra-chave <u>ou</u> modalidade escolhida. UF, situação e prazo continuam restringindo</small></span></label>
        </fieldset>
        <label class="toggle"><span><b>Somente abertas</b><br><span class="small muted">Recebendo propostas agora</span></span>
          <span class="switch"><input type="checkbox" name="abertas" ${f.abertas === "true" ? raw("checked") : ""}><span></span></span></label>
        <div class="field"><label>Estado (UF)</label>${grupo("uf", Object.fromEntries(UFS.map((u) => [u, u])), sel("uf"))}</div>
        <div class="field"><label>Município</label><input class="input" name="municipio" value="${f.municipio || ""}" placeholder="Parte do nome"></div>
        <div class="field"><label>Modalidade</label>${grupo("modalidade", MODALIDADES, sel("modalidade"))}</div>
        <div class="field"><label>Situação</label>${grupo("status", STATUS, sel("status"))}</div>
        <div class="grid2">
          <div class="field"><label>Valor mínimo (R$)</label><input class="input" name="valor_min" type="number" inputmode="decimal" min="0" value="${f.valor_min || ""}"></div>
          <div class="field"><label>Valor máximo (R$)</label><input class="input" name="valor_max" type="number" inputmode="decimal" min="0" value="${f.valor_max || ""}"></div>
        </div>
        <div class="grid2">
          <div class="field"><label>Publicada de</label><input class="input" name="publicacao_de" type="date" value="${f.publicacao_de || ""}"></div>
          <div class="field"><label>Publicada até</label><input class="input" name="publicacao_ate" type="date" value="${f.publicacao_ate || ""}"></div>
        </div>
      </div>`;
  }

  function lerFiltros(root) {
    const f = {};
    for (const k of ["q", "municipio", "valor_min", "valor_max", "publicacao_de", "publicacao_ate"]) {
      const el = $(`[name="${k}"]`, root);
      if (el && el.value.trim()) f[k] = el.value.trim();
    }
    for (const k of ["uf", "modalidade", "status"]) {
      const v = $$(`[name="${k}"]:checked`, root).map((e) => e.value);
      if (v.length) f[k] = v.join(",");
    }
    if ($('[name="abertas"]', root)?.checked) f.abertas = "true";
    if ($('[name="combinar"]:checked', root)?.value === "qualquer") f.combinar = "qualquer";
    const tags = $("[data-tags]", root);
    if (tags && tags._lista && tags._lista.length) f.palavras = tags._lista.join(",");
    return f;
  }

  const MAX_PALAVRAS = 60;

  /** Chips dos filtros. Palavras-chave: um chip cada, até `max`, depois "+N" (não estoura o layout). */
  function chipsFiltros(f, max = 6) {
    const kws = lista(f.palavras);
    const resto = { ...f };
    delete resto.palavras;
    const base = resumoFiltros(resto).map((t) => html`<span class="chip">${t}</span>`);
    const vistas = kws.slice(0, max).map((k) => html`<span class="chip kw">${k}</span>`);
    const extra = kws.length > max ? html`<span class="chip gray">+${kws.length - max}</span>` : "";
    return html`${vistas}${extra}${base}`;
  }

  /** Campo de palavras-chave em chips (adicionar/remover). Estado em `el._lista`. */
  function montarTags(root) {
    const el = $("[data-tags]", root);
    if (!el) return;
    const input = $("[data-tag-input]", el), lista_ = $("[data-tags-lista]", el), info = $("[data-tags-info]", el);
    el._lista = lista(el.dataset.valor);

    const pintar = () => {
      lista_.innerHTML = val(el._lista.map((t, i) => html`
        <span class="chip kw">${t}<button type="button" data-tag-del="${i}" aria-label="Remover ${t}">×</button></span>`));
      info.textContent = el._lista.length
        ? `${el._lista.length} de ${MAX_PALAVRAS} palavras` : "Nenhuma palavra adicionada.";
    };
    const adicionar = (texto) => {
      let aviso = "";
      for (const parte of String(texto).split(/[,;\n]+/)) {
        const t = parte.replace(/\s+/g, " ").trim().slice(0, 60);
        if (!t) continue;
        if (el._lista.some((x) => x.toLowerCase() === t.toLowerCase())) continue;
        if (el._lista.length >= MAX_PALAVRAS) { aviso = `Limite de ${MAX_PALAVRAS} palavras.`; break; }
        el._lista.push(t);
      }
      pintar();
      if (aviso) toast(aviso, true);
    };
    $("[data-tag-add]", el).onclick = () => { adicionar(input.value); input.value = ""; input.focus(); };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        adicionar(input.value);
        input.value = "";
      }
    });
    input.addEventListener("paste", (e) => {
      const txt = (e.clipboardData || window.clipboardData)?.getData("text") || "";
      if (/[,;\n]/.test(txt)) { e.preventDefault(); adicionar(txt); }
    });
    lista_.addEventListener("click", (e) => {
      const b = e.target.closest("[data-tag-del]");
      if (!b) return;
      el._lista.splice(Number(b.dataset.tagDel), 1);
      pintar();
    });
    pintar();
  }

  function resumoFiltros(f) {
    return Object.entries(limpar(f)).filter(([k]) => ROTULOS[k]).map(([k, v]) => {
      let t = v;
      if (k === "modalidade") t = lista(v).map((x) => MODALIDADES[x] || x).join(", ");
      else if (k === "status") t = lista(v).map((x) => STATUS[x] || x).join(", ");
      else if (k === "abertas") return ROTULOS[k];
      else if (k === "combinar") return v === "qualquer" ? "Somando critérios" : null;
      else if (k.startsWith("valor")) t = brl.format(Number(v));
      else if (k.startsWith("publicacao")) t = fmtData(v);
      return `${ROTULOS[k]}: ${t}`;
    }).filter(Boolean);
  }

  /* ===================== Sheet ===================== */
  function abrirSheet(conteudo, onMount) {
    const s = $("#sheet");
    s.innerHTML = val(html`<div class="grabber"></div>${conteudo}`);
    s.hidden = false;
    $("#sheet-backdrop").hidden = false;
    document.body.style.overflow = "hidden";
    $("#sheet-backdrop").onclick = fecharSheet;
    $$("[data-fechar]", s).forEach((b) => (b.onclick = fecharSheet));
    onMount && onMount(s);
  }
  function fecharSheet() {
    $("#sheet").hidden = true;
    $("#sheet-backdrop").hidden = true;
    document.body.style.overflow = "";
  }

  /* ===================== Componentes de tela ===================== */
  function cardLicitacao(l) {
    const p = prazo(l.data_encerramento_propostas);
    return html`
      <a class="card" href="#/licitacao/${l.id}">
        <div class="row between" style="align-items:flex-start;gap:10px">
          <h3 class="grow">${l.orgao}</h3>
          <span class="chip ${statusCls(l.status)}">${l.status_display}</span>
        </div>
        <p class="objeto">${l.objeto}</p>
        <div class="row between">
          <span class="valor">${fmtValor(l.valor_estimado)}</span>
          ${p && l.status !== "encerrada" ? html`<span class="chip ${p.cls}">${p.txt}</span>` : ""}
        </div>
        <div class="meta" style="margin-top:8px">
          <span>${l.modalidade_display}</span>
          ${l.uf ? html`<span>${l.municipio ? l.municipio + " / " : ""}${l.uf}</span>` : ""}
          <span>Publ. ${fmtData(l.data_publicacao)}</span>
        </div>
      </a>`;
  }

  const vazio = (titulo, texto, extra = "") => html`
    <div class="empty">${raw(icons.inbox)}<h2>${titulo}</h2><p>${texto}</p>${extra}</div>`;
  const carregando = () => html`<div class="stack"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>`;
  const erroHTML = (e) => vazio("Não foi possível carregar", e instanceof ApiError ? e.texto : navigator.onLine ? "Tente novamente em instantes." : "Você está sem conexão.",
    html`<p style="margin-top:16px"><button class="btn" data-act="reload">Tentar novamente</button></p>`);

  /* ===================== Telas ===================== */
  const view = () => $("#view");
  let renderId = 0;

  function setChrome({ titulo, voltar = false, tab = null, acoes = "" }) {
    $("#page-title").textContent = titulo;
    $("#btn-back").hidden = !voltar;
    $("#topbar-actions").innerHTML = val(acoes);
    $("#tabbar").classList.toggle("hidden", !tab && voltar);
    view().classList.toggle("no-tabbar", !tab && voltar);
    $$("#tabbar a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
    document.title = titulo === "Licitações" ? "Busca Licitações" : `${titulo} · Licitações`;
  }

  /* ---- Busca ---- */
  function novaBusca() { return { filtros: {}, ordering: "", itens: [], page: 0, count: null, fim: false, carregando: false }; }

  function aplicarFiltros(filtros) {
    Object.assign(state.busca, { filtros, itens: [], page: 0, count: null, fim: false });
  }

  async function telaBusca() {
    state.busca ||= novaBusca();
    const b = state.busca;
    const n = contarFiltros(b.filtros);
    setChrome({ titulo: "Licitações", tab: "busca" });
    view().innerHTML = val(html`
      <div class="stack">
        <form class="searchbar" id="form-busca" role="search">
          <input class="input" type="search" name="q" value="${b.filtros.q || ""}" placeholder="Buscar licitações…" enterkeyhint="search" aria-label="Palavra-chave">
          <button class="btn" aria-label="Buscar">${raw(icons.search)}</button>
          <button class="btn ghost filter-btn" type="button" data-act="filtros" aria-label="Filtros">${raw(icons.filter)}${n > (b.filtros.q ? 1 : 0) ? html`<span class="dot">${n - (b.filtros.q ? 1 : 0)}</span>` : ""}</button>
        </form>
        <div class="row between">
          <span class="small muted" id="contagem"></span>
          <select class="input" id="ordenacao" style="width:auto;min-height:38px;padding:4px 30px 4px 12px;font-size:13px" aria-label="Ordenar por">
            ${Object.entries(ORDENACOES).map(([v, t]) => html`<option value="${v}" ${b.ordering === v ? raw("selected") : ""}>${t}</option>`)}
          </select>
        </div>
        ${contarFiltros(b.filtros) ? html`<div class="chips">${chipsFiltros(b.filtros, 8)}</div>` : ""}
        <div id="resultados" class="stack"></div>
        <div id="mais" class="center"></div>
      </div>`);
    $("#form-busca").onsubmit = (e) => {
      e.preventDefault();
      const q = new FormData(e.target).get("q").trim();
      aplicarFiltros(limpar({ ...b.filtros, q }));
      telaBusca();
    };
    $("#ordenacao").onchange = (e) => { b.ordering = e.target.value; buscar(true); };
    if (b.itens.length || b.count === 0) pintarResultados();
    else buscar(true);
  }

  function paramsBusca(b, page) {
    const p = new URLSearchParams(limpar(b.filtros));
    if (b.ordering) p.set("ordering", b.ordering);
    p.set("page", page);
    p.set("page_size", 20);
    return p;
  }

  async function buscar(reset) {
    const b = state.busca;
    if (b.carregando) return;
    if (reset) Object.assign(b, { itens: [], page: 0, count: null, fim: false });
    if (b.fim) return;
    b.carregando = true;
    const box = $("#resultados");
    if (reset && box) box.innerHTML = val(carregando());
    try {
      const d = await api(`/licitacoes/?${paramsBusca(b, b.page + 1)}`);
      b.page += 1;
      b.count = d.count;
      b.itens.push(...d.results);
      b.fim = !d.next;
    } catch (e) {
      b.carregando = false;
      if (box && !b.itens.length) box.innerHTML = val(erroHTML(e));
      else toast(e.texto || "Falha ao carregar", true);
      return;
    }
    b.carregando = false;
    pintarResultados();
  }

  function pintarResultados() {
    const b = state.busca;
    const box = $("#resultados");
    if (!box) return;
    $("#contagem").textContent = b.count == null ? "" : `${b.count.toLocaleString("pt-BR")} resultado${b.count === 1 ? "" : "s"}`;
    box.innerHTML = b.itens.length
      ? val(b.itens.map(cardLicitacao))
      : val(vazio("Nenhuma licitação encontrada", "Tente outras palavras ou remova alguns filtros."));
    const mais = $("#mais");
    mais.innerHTML = val(html`
      ${!b.fim ? html`<button class="btn ghost block" data-act="mais">Carregar mais</button>` : ""}
      ${b.itens.length && contarFiltros(b.filtros) ? html`<button class="btn secondary block" style="margin-top:12px" data-act="salvar-alerta">${raw(icons.bell)} Criar alerta com estes filtros</button>` : ""}`);
  }

  function abrirFiltros() {
    const b = state.busca;
    abrirSheet(html`
      <div class="sheet-head"><h2 class="title">Filtros</h2><button class="icon-btn" data-fechar aria-label="Fechar" style="color:var(--text)">${raw(icons.close)}</button></div>
      <form id="form-filtros">${filtrosHTML(b.filtros)}
        <div class="sheet-foot">
          <button type="button" class="btn ghost" data-act="limpar-filtros">Limpar</button>
          <button class="btn">Aplicar filtros</button>
        </div>
      </form>`, (s) => {
      $("#form-filtros", s).onsubmit = (e) => {
        e.preventDefault();
        aplicarFiltros(lerFiltros(s));
        fecharSheet();
        telaBusca();
      };
    });
  }

  /* ---- Detalhe ---- */
  async function telaDetalhe(id) {
    setChrome({ titulo: "Licitação", voltar: true });
    const rid = ++renderId;
    view().innerHTML = val(carregando());
    let l;
    try { l = await api(`/licitacoes/${id}/`); } catch (e) {
      if (rid === renderId) view().innerHTML = val(erroHTML(e));
      return;
    }
    if (rid !== renderId) return;
    const p = prazo(l.data_encerramento_propostas);
    view().innerHTML = val(html`
      <div class="stack">
        <div class="card stack">
          <div class="chips">
            <span class="chip ${statusCls(l.status)}">${l.status_display}</span>
            <span class="chip gray">${l.modalidade_display}</span>
            ${p && l.status !== "encerrada" ? html`<span class="chip ${p.cls}">${p.txt}</span>` : ""}
          </div>
          <h2 class="title" style="font-size:18px">${l.orgao.razao_social}</h2>
          <p>${l.objeto}</p>
          <div class="valor" style="font-size:20px">${fmtValor(l.valor_estimado)}</div>
        </div>
        <dl class="card dl" style="margin:0">
          <div><dt>Número</dt><dd>${l.numero || "—"}</dd></div>
          <div><dt>Local</dt><dd>${[l.municipio, l.uf].filter(Boolean).join(" / ") || "—"}</dd></div>
          <div><dt>Publicação</dt><dd>${fmtData(l.data_publicacao)}</dd></div>
          <div><dt>Abertura das propostas</dt><dd>${fmtDataHora(l.data_abertura)}</dd></div>
          <div><dt>Encerramento das propostas</dt><dd>${fmtDataHora(l.data_encerramento_propostas)}</dd></div>
          <div class="divider"></div>
          <div><dt>Órgão</dt><dd>${l.orgao.razao_social}${l.orgao.cnpj ? html`<br><span class="muted small">CNPJ ${l.orgao.cnpj}</span>` : ""}</dd></div>
          <div><dt>Fonte</dt><dd>${l.fonte}</dd></div>
        </dl>
        ${/^https?:\/\//i.test(l.link_original || "") ? html`<a class="btn block" href="${l.link_original}" target="_blank" rel="noopener noreferrer">Abrir edital na fonte ${raw(icons.ext)}</a>` : ""}
        <button class="btn ghost block" data-act="compartilhar" data-id="${l.id}">Compartilhar</button>
      </div>`);
    view().dataset.titulo = l.orgao.razao_social;
  }

  /* ---- Auth ---- */
  function telaLogin() {
    setChrome({ titulo: "Entrar" });
    $("#tabbar").classList.add("hidden");
    view().classList.add("no-tabbar");
    view().innerHTML = val(html`
      <div class="stack">
        <div class="hero"><img src="/static/app/icon-192.png" alt=""><h2>Busca Licitações</h2><p class="muted">Acesso restrito. Entre com sua conta.</p></div>
        <form class="stack" id="form-login" novalidate>
          <div class="field"><label>Usuário</label><input class="input" name="username" autocomplete="username" autocapitalize="none" required></div>
          <div class="field"><label>Senha</label><input class="input" name="password" type="password" autocomplete="current-password" required></div>
          <p class="error small" id="erro" style="color:var(--secondary)" hidden></p>
          <button class="btn block">Entrar</button>
        </form>
        <p class="center small muted">Não tem acesso? Peça um convite a quem administra o aplicativo.</p>
      </div>`);
    $("#form-login").onsubmit = async (e) => {
      e.preventDefault();
      const btn = $("button", e.target); btn.disabled = true;
      const fd = Object.fromEntries(new FormData(e.target));
      try {
        const t = await api("/auth/token/", { method: "POST", body: fd, auth: false });
        session.set(t);
        await carregarUsuario();
        atualizarBadge();
        location.hash = state.next && !/^#\/(login|cadastro)/.test(state.next) ? state.next : "#/";
        state.next = null;
      } catch (err) {
        const el = $("#erro"); el.textContent = err.status === 401 ? "Usuário ou senha incorretos." : err.texto; el.hidden = false;
        btn.disabled = false;
      }
    };
  }

  async function telaCadastro(query) {
    setChrome({ titulo: "Criar conta" });
    $("#tabbar").classList.add("hidden");
    view().classList.add("no-tabbar");
    const token = new URLSearchParams(query).get("token") || "";
    view().innerHTML = val(carregando());

    const invalido = (msg) => {
      view().innerHTML = val(html`<div class="stack">${vazio("Convite indisponível", msg,
        html`<p style="margin-top:16px"><a class="btn" href="#/login">Ir para o login</a></p>`)}</div>`);
    };
    if (!token) return invalido("O link do convite está incompleto. Use o link enviado por e-mail.");
    if (session.get()) {
      view().innerHTML = val(html`<div class="stack">${vazio("Você já está conectado",
        "Para usar um convite, saia da conta atual primeiro.",
        html`<p style="margin-top:16px"><button class="btn" data-act="sair-cadastro" data-token="${token}">Sair e continuar</button></p>`)}</div>`);
      return;
    }
    let convite;
    try {
      convite = await api(`/auth/convites/validar/?token=${encodeURIComponent(token)}`, { auth: false });
    } catch (e) {
      return invalido(e.status === 404 ? "Este convite é inválido, expirou ou já foi utilizado. Peça um novo convite." : e.texto);
    }

    view().innerHTML = val(html`
      <form class="stack" id="form-reg" novalidate>
        <div class="hero"><img src="/static/app/icon-192.png" alt=""><h2>Crie sua conta</h2>
          <p class="muted">Convite para <b>${convite.email}</b></p></div>
        <div class="field"><label>Nome de usuário</label><input class="input" name="username" autocomplete="username" autocapitalize="none" required><span class="error" data-erro="username"></span></div>
        <div class="grid2">
          <div class="field"><label>Nome</label><input class="input" name="first_name" autocomplete="given-name"></div>
          <div class="field"><label>Sobrenome</label><input class="input" name="last_name" autocomplete="family-name"></div>
        </div>
        <div class="field"><label>Senha</label><input class="input" name="password" type="password" autocomplete="new-password" minlength="8" required><span class="error" data-erro="password"></span></div>
        <p class="small muted">Mínimo de 8 caracteres, sem ser comum ou só números.</p>
        <p class="error small" id="erro" style="color:var(--secondary)" hidden></p>
        <button class="btn block">Criar conta e entrar</button>
      </form>`);
    $("#form-reg").onsubmit = async (e) => {
      e.preventDefault();
      const btn = $("button", e.target); btn.disabled = true;
      $$("[data-erro]").forEach((x) => (x.textContent = ""));
      $("#erro").hidden = true;
      const fd = { ...Object.fromEntries(new FormData(e.target)), token };
      try {
        await api("/auth/register/", { method: "POST", body: fd, auth: false });
        session.set(await api("/auth/token/", { method: "POST", body: { username: fd.username, password: fd.password }, auth: false }));
        await carregarUsuario();
        toast("Conta criada!");
        location.hash = "#/";
      } catch (err) {
        btn.disabled = false;
        const geral = [];
        if (err.data && typeof err.data === "object") {
          for (const [k, v] of Object.entries(err.data)) {
            const el = $(`[data-erro="${k}"]`);
            const txt = Array.isArray(v) ? v.join(" ") : String(v);
            if (el) el.textContent = txt; else geral.push(txt);
          }
        } else geral.push("Não foi possível criar a conta.");
        if (geral.length) { const el = $("#erro"); el.textContent = geral.join(" "); el.hidden = false; }
      }
    };
  }

  async function telaRedefinirSenha(query) {
    setChrome({ titulo: "Nova senha" });
    $("#tabbar").classList.add("hidden");
    view().classList.add("no-tabbar");
    const q = new URLSearchParams(query);
    const uid = q.get("uid") || "", token = q.get("token") || "";
    view().innerHTML = val(carregando());

    const invalido = (msg) => {
      view().innerHTML = val(html`<div class="stack">${vazio("Link indisponível", msg,
        html`<p style="margin-top:16px"><a class="btn" href="#/login">Ir para o login</a></p>`)}</div>`);
    };
    if (!uid || !token) return invalido("O link está incompleto. Use o link enviado por e-mail.");
    let info;
    try {
      info = await api(`/auth/senha/validar/?uid=${encodeURIComponent(uid)}&token=${encodeURIComponent(token)}`, { auth: false });
    } catch (e) {
      return invalido(e.status === 404 ? "Este link é inválido, expirou ou já foi utilizado. Peça um novo ao administrador." : e.texto);
    }

    view().innerHTML = val(html`
      <form class="stack" id="form-nova-senha" novalidate>
        <div class="hero"><img src="/static/app/icon-192.png" alt=""><h2>Crie uma nova senha</h2>
          <p class="muted">Conta <b>${info.username}</b></p></div>
        <div class="field"><label>Nova senha</label>
          <input class="input" name="password" type="password" autocomplete="new-password" minlength="8" required>
          <span class="error" data-erro="password"></span></div>
        <div class="field"><label>Repita a nova senha</label>
          <input class="input" name="password2" type="password" autocomplete="new-password" minlength="8" required></div>
        <p class="small muted">Mínimo de 8 caracteres, sem ser comum ou só números.</p>
        <p class="error small" id="erro" style="color:var(--secondary)" hidden></p>
        <button class="btn block">Salvar nova senha</button>
      </form>`);
    $("#form-nova-senha").onsubmit = async (e) => {
      e.preventDefault();
      const f = e.target, btn = $("button", f), erro = $("#erro");
      erro.hidden = true;
      $$("[data-erro]").forEach((x) => (x.textContent = ""));
      if (f.password.value !== f.password2.value) {
        erro.textContent = "As senhas não conferem."; erro.hidden = false; return;
      }
      btn.disabled = true;
      try {
        await api("/auth/senha/confirmar/", { method: "POST", auth: false, body: { uid, token, password: f.password.value } });
        session.clear(); state.user = null;
        toast("Senha alterada. Entre com a nova senha.");
        location.hash = "#/login";
      } catch (err) {
        btn.disabled = false;
        const d = err.data || {};
        if (d.password) $('[data-erro="password"]').textContent = [].concat(d.password).join(" ");
        else { erro.textContent = err.texto; erro.hidden = false; }
      }
    };
  }

  function exigirLogin() {
    if (session.get()) return true;
    state.next = location.hash;
    location.hash = "#/login";
    return false;
  }

  /* ---- Alertas ---- */
  async function telaAlertas() {
    if (!exigirLogin()) return;
    setChrome({ titulo: "Meus alertas", tab: "alertas", acoes: html`<a class="icon-btn" href="#/alertas/novo" aria-label="Novo alerta">${raw(icons.plus)}</a>` });
    const rid = ++renderId;
    view().innerHTML = val(carregando());
    let d;
    try { d = await api("/alertas/?page_size=100"); } catch (e) {
      if (rid === renderId && e.status !== 401) view().innerHTML = val(erroHTML(e));
      else if (e.status === 401) { exigirLogin(); }
      return;
    }
    if (rid !== renderId) return;
    if (!d.results.length) {
      view().innerHTML = val(vazio("Nenhum alerta ainda", "Salve uma busca e avisamos quando surgirem licitações novas.",
        html`<p style="margin-top:16px"><a class="btn" href="#/alertas/novo">Criar alerta</a></p>`));
      return;
    }
    view().innerHTML = val(html`<div class="stack">${d.results.map((a) => html`
      <div class="card stack" data-alerta="${a.id}">
        <div class="row between">
          <h3 class="grow" style="font-size:16px">${a.nome}</h3>
          ${a.nao_lidas ? html`<a href="#/notificacoes?alerta=${a.id}" class="chip red">${a.nao_lidas} nova${a.nao_lidas > 1 ? "s" : ""}</a>` : ""}
        </div>
        <div class="chips">${chipsFiltros(a.filtros, 6)}</div>
        <label class="toggle"><span class="small">${a.ativo ? "Ativo" : "Pausado"}${a.notificar_email ? " · avisa por e-mail" : ""}</span>
          <span class="switch"><input type="checkbox" data-act="toggle-alerta" data-id="${a.id}" ${a.ativo ? raw("checked") : ""}><span></span></span></label>
        <div class="row">
          <a class="btn small grow" href="#/alertas/${a.id}/resultados">Ver licitações</a>
          <a class="btn small ghost" href="#/alertas/${a.id}/editar">Editar</a>
          <button class="btn small ghost red" data-act="excluir-alerta" data-id="${a.id}" aria-label="Excluir alerta">Excluir</button>
        </div>
      </div>`)}</div>`);
  }

  async function telaAlertaForm(id, filtrosIniciais) {
    if (!exigirLogin()) return;
    setChrome({ titulo: id ? "Editar alerta" : "Novo alerta", voltar: true });
    const rid = ++renderId;
    let alerta = { nome: "", filtros: filtrosIniciais || {}, notificar_email: false, ativo: true };
    if (id) {
      view().innerHTML = val(carregando());
      try { alerta = await api(`/alertas/${id}/`); } catch (e) {
        if (rid === renderId) view().innerHTML = val(erroHTML(e));
        return;
      }
      if (rid !== renderId) return;
    }
    view().innerHTML = val(html`
      <form class="stack" id="form-alerta">
        <div class="field"><label>Nome do alerta</label><input class="input" name="nome" value="${alerta.nome}" placeholder="Ex.: TI em São Paulo" maxlength="150" required></div>
        ${filtrosHTML(alerta.filtros, { tags: true })}
        <label class="toggle"><span><b>Avisar por e-mail</b><br><span class="small muted">${state.user?.email ? "Enviado para " + state.user.email : "Resumo das novas licitações"}</span></span>
          <span class="switch"><input type="checkbox" name="notificar_email" ${alerta.notificar_email ? raw("checked") : ""}><span></span></span></label>
        <label class="toggle"><span><b>Notificar no celular</b><br><span class="small muted">Push, se ativado na aba Conta</span></span>
          <span class="switch"><input type="checkbox" name="notificar_push" ${alerta.notificar_push !== false ? raw("checked") : ""}><span></span></span></label>
        <label class="toggle"><span><b>Alerta ativo</b></span>
          <span class="switch"><input type="checkbox" name="ativo" ${alerta.ativo ? raw("checked") : ""}><span></span></span></label>
        <p class="small" id="erro" style="color:var(--secondary)" hidden></p>
        <button class="btn block">Salvar alerta</button>
      </form>`);
    montarTags($("#form-alerta"));
    $("#form-alerta").onsubmit = async (e) => {
      e.preventDefault();
      const f = e.target, btn = $("button.btn.block", f);
      const filtros = lerFiltros(f);
      const body = {
        nome: f.nome.value.trim(), filtros,
        notificar_email: f.notificar_email.checked, notificar_push: f.notificar_push.checked,
        ativo: f.ativo.checked,
      };
      if (!Object.keys(filtros).length) {
        const el = $("#erro"); el.textContent = "Informe ao menos um filtro."; el.hidden = false; return;
      }
      btn.disabled = true;
      try {
        await api(id ? `/alertas/${id}/` : "/alertas/", { method: id ? "PUT" : "POST", body });
        toast("Alerta salvo");
        location.hash = "#/alertas";
      } catch (err) {
        btn.disabled = false;
        const el = $("#erro"); el.textContent = err.texto; el.hidden = false;
      }
    };
  }

  async function telaResultadosAlerta(id) {
    if (!exigirLogin()) return;
    setChrome({ titulo: "Resultados do alerta", voltar: true });
    const rid = ++renderId;
    view().innerHTML = val(carregando());
    try {
      const d = await api(`/alertas/${id}/resultados/?page_size=50`);
      if (rid !== renderId) return;
      view().innerHTML = val(d.results.length
        ? html`<div class="stack"><p class="small muted">${d.count.toLocaleString("pt-BR")} licitação(ões)</p>${d.results.map(cardLicitacao)}</div>`
        : vazio("Nada por aqui ainda", "Nenhuma licitação atual casa com este alerta."));
    } catch (e) { if (rid === renderId) view().innerHTML = val(erroHTML(e)); }
  }

  /* ---- Notificações ---- */
  async function telaNotificacoes(query) {
    if (!exigirLogin()) return;
    const alerta = new URLSearchParams(query).get("alerta");
    setChrome({
      titulo: "Novidades", tab: "notificacoes",
      acoes: html`<button class="btn text" style="color:#fff" data-act="marcar-todas">Marcar lidas</button>`,
    });
    const rid = ++renderId;
    view().innerHTML = val(carregando());
    try {
      const d = await api(`/notificacoes/?page_size=50${alerta ? "&alerta=" + encodeURIComponent(alerta) : ""}`);
      if (rid !== renderId) return;
      view().innerHTML = val(d.results.length ? html`<div class="stack">${d.results.map((n) => html`
        <div class="stack" data-notif="${n.id}" style="gap:6px">
          <div class="row between small muted"><span class="chip ${n.lida ? "gray" : "red"}">${n.alerta_nome}</span><span>${fmtDataHora(n.criado_em)}</span></div>
          <div class="${n.lida ? "" : "unread"}" style="border-radius:var(--radius)" data-act="abrir-notif" data-id="${n.id}" data-lic="${n.licitacao.id}">${cardLicitacao(n.licitacao)}</div>
        </div>`)}</div>`
        : vazio("Sem novidades", "Quando surgirem licitações que casem com seus alertas, elas aparecem aqui."));
    } catch (e) { if (rid === renderId && e.status !== 401) view().innerHTML = val(erroHTML(e)); }
  }

  async function atualizarBadge() {
    const b = $("#badge-notif");
    if (!session.get()) { b.hidden = true; return; }
    try {
      const d = await api("/notificacoes/?lida=false&page_size=1");
      state.naoLidas = d.count;
      b.textContent = d.count > 99 ? "99+" : d.count;
      b.hidden = d.count === 0;
      if ("setAppBadge" in navigator) (d.count ? navigator.setAppBadge(d.count) : navigator.clearAppBadge()).catch(() => {});
    } catch { /* offline */ }
  }

  /* ---- Conta ---- */
  async function telaConta() {
    setChrome({ titulo: "Conta", tab: "conta" });
    if (!state.user) await carregarUsuario();
    const u = state.user;
    if (!u) { exigirLogin(); return; }
    const sub = await push.atual();
    const permNegada = push.suportado() && Notification.permission === "denied";
    const pushHTML = !push.suportado()
      ? html`<div class="card small muted">Notificações push não são suportadas neste navegador.${/iphone|ipad|ipod/i.test(navigator.userAgent) ? " No iPhone, instale o app na Tela de Início (iOS 16.4+)." : ""}</div>`
      : html`<div class="card stack">
          <div class="row between"><div class="grow"><b>Notificações no celular</b>
            <div class="small muted">${permNegada ? "Bloqueadas nas configurações do navegador." : sub ? "Ativadas neste aparelho." : "Receba um aviso quando surgirem licitações dos seus alertas."}</div></div>
            ${sub ? html`<span class="chip green">Ativas</span>` : ""}</div>
          ${sub ? html`<button class="btn ghost" data-act="push-desativar">Desativar neste aparelho</button>
                       <button class="btn text" data-act="push-testar">Ver exemplo</button>`
                : permNegada ? "" : html`<button class="btn" data-act="push-ativar">Ativar notificações</button>`}
        </div>`;
    view().innerHTML = val(html`
      <div class="stack">
        <div class="card row">
          <div class="chip" style="width:48px;height:48px;border-radius:50%;justify-content:center;font-size:20px">${(u.first_name || u.username)[0].toUpperCase()}</div>
          <div class="grow"><b>${[u.first_name, u.last_name].filter(Boolean).join(" ") || u.username}</b><div class="small muted">${u.email || "sem e-mail"}</div></div>
        </div>
        <form class="card stack" id="form-conta">
          <div class="grid2">
            <div class="field"><label>Nome</label><input class="input" name="first_name" value="${u.first_name}" autocomplete="given-name"></div>
            <div class="field"><label>Sobrenome</label><input class="input" name="last_name" value="${u.last_name}" autocomplete="family-name"></div>
          </div>
          <div class="field"><label>E-mail</label><input class="input" name="email" type="email" value="${u.email}" autocomplete="email"></div>
          <button class="btn">Salvar dados</button>
        </form>
        ${u.is_superuser ? html`<div class="card stack" id="box-convites">
          <div><b>Convidar pessoas</b>
            <div class="small muted">Enviamos um e-mail com um link de cadastro de uso único.</div></div>
          <form class="stack" id="form-convite" novalidate>
            <div class="field"><label>E-mail da pessoa</label>
              <input class="input" type="email" name="email" inputmode="email" autocapitalize="none" placeholder="nome@exemplo.com" required></div>
            <p class="small" id="erro-convite" style="color:var(--secondary)" hidden></p>
            <button class="btn">Enviar convite</button>
          </form>
          <div id="convites-lista"></div>
        </div>
        <div class="card stack">
          <div><b>Redefinir senha de um usuário</b>
            <div class="small muted">Enviamos um e-mail com um link para a pessoa criar uma nova senha.</div></div>
          <form class="stack" id="form-senha" novalidate>
            <div class="field"><label>E-mail do usuário</label>
              <input class="input" type="email" name="email" inputmode="email" autocapitalize="none" placeholder="nome@exemplo.com" required></div>
            <p class="small" id="erro-senha" style="color:var(--secondary)" hidden></p>
            <button class="btn secondary">Enviar e-mail de redefinição</button>
          </form>
        </div>
        <div class="card stack">
          <div class="row between"><div><b>Atualização automática</b>
            <div class="small muted">O servidor busca novas licitações sozinho, todos os dias.</div></div>
            <button class="btn text small" data-act="fontes-recarregar" aria-label="Atualizar situação">Atualizar</button></div>
          <div id="fontes-lista"><div class="spinner"></div></div>
        </div>` : ""}
        ${pushHTML}
        ${instalarHTML()}
        <button class="btn ghost red block" data-act="sair">Sair da conta</button>
      </div>`);
    if (u.is_superuser) { montarConvites(); montarSenha(); carregarFontes(); }
    $("#form-conta").onsubmit = async (e) => {
      e.preventDefault();
      try {
        state.user = await api("/auth/me/", { method: "PATCH", body: Object.fromEntries(new FormData(e.target)) });
        toast("Dados atualizados");
        telaConta();
      } catch (err) { toast(err.texto, true); }
    };
  }

  async function carregarConvites() {
    const box = $("#convites-lista");
    if (!box) return;
    try {
      const itens = await api("/auth/convites/");
      box.innerHTML = val(itens.length ? html`
        <div class="divider"></div>
        <div class="stack" style="gap:10px">${itens.slice(0, 20).map((c) => html`
          <div class="row between">
            <div class="grow"><div style="overflow-wrap:anywhere">${c.email}</div>
              <div class="small muted">${c.status === "usado" ? "Cadastrado em " + fmtData(c.usado_em)
                : c.status === "expirado" ? "Expirou em " + fmtData(c.expira_em) : "Válido até " + fmtData(c.expira_em)}</div></div>
            <span class="chip ${c.status === "usado" ? "green" : c.status === "expirado" ? "gray" : ""}">${c.status}</span>
            ${c.status !== "usado" ? html`<button class="btn text small" data-act="revogar-convite" data-id="${c.id}" aria-label="Remover convite" style="color:var(--secondary)">Remover</button>` : ""}
          </div>`)}</div>` : "");
    } catch (e) { box.innerHTML = val(html`<p class="small muted">${e.texto}</p>`); }
  }

  function montarConvites() {
    carregarConvites();
    $("#form-convite").onsubmit = async (e) => {
      e.preventDefault();
      const f = e.target, btn = $("button", f), erro = $("#erro-convite");
      erro.hidden = true;
      btn.disabled = true;
      try {
        const r = await api("/auth/convites/", { method: "POST", body: { email: f.email.value.trim() } });
        f.reset();
        state.ultimoLink = r.link;
        mostrarLinkConvite(r);
        carregarConvites();
      } catch (err) {
        erro.textContent = err.texto; erro.hidden = false;
      }
      btn.disabled = false;
    };
  }

  /** "há 12 min" / "em 3 h" a partir de um ISO. */
  function relativo(iso) {
    if (!iso) return "—";
    const min = Math.round((new Date(iso) - Date.now()) / 60000);
    const a = Math.abs(min);
    const t = a < 60 ? `${a} min` : a < 1440 ? `${Math.round(a / 60)} h` : `${Math.round(a / 1440)} d`;
    if (min <= 0 && a < 2) return "agora";
    return min < 0 ? `há ${t}` : `em ${t}`;
  }

  async function carregarFontes() {
    const box = $("#fontes-lista");
    if (!box) return;
    try {
      const fontes = await api("/fontes/status/");
      box.innerHTML = val(html`<div class="stack" style="gap:12px">${fontes.map((f) => {
        const u = f.ultimo;
        const rodando = u && u.status === "em_execucao";
        const [cls, rotulo] = !f.ativo ? ["gray", "pausada"]
          : f.atrasada ? ["red", "atrasada"]
          : rodando ? ["", "sincronizando"]
          : u && u.status === "erro" ? ["red", "erro"]
          : u && u.status === "parcial" ? ["", "parcial"]
          : ["green", "em dia"];
        return html`
          <div class="stack" style="gap:6px">
            <div class="row between"><b style="overflow-wrap:anywhere;min-width:0">${f.nome}</b><span class="chip ${cls}">${rotulo}</span></div>
            <div class="small muted">${f.total_licitacoes.toLocaleString("pt-BR")} licitações ·
              última execução ${relativo(u && (u.finalizado_em || u.iniciado_em))}${u && u.status !== "em_execucao" ? ` (${u.itens} itens)` : ""} ·
              próxima ${f.ativo ? relativo(f.proxima_em) : "—"}</div>
            ${u && u.erro ? html`<div class="small" style="color:var(--secondary);overflow-wrap:anywhere">${u.erro.split("\n")[0]}</div>` : ""}
            <div><button class="btn ghost small" data-act="sync-agora" data-id="${f.id}" ${rodando ? raw("disabled") : ""}>Sincronizar agora</button></div>
          </div>`;
      })}</div>`);
    } catch (e) { box.innerHTML = val(html`<p class="small muted">${e.texto}</p>`); }
  }

  function montarSenha() {
    $("#form-senha").onsubmit = async (e) => {
      e.preventDefault();
      const f = e.target, btn = $("button", f), erro = $("#erro-senha");
      erro.hidden = true;
      btn.disabled = true;
      try {
        const r = await api("/auth/senha/enviar/", { method: "POST", body: { email: f.email.value.trim() } });
        f.reset();
        state.ultimoLink = r.link;
        abrirSheet(html`
          <h2 class="title">${r.email_enviado ? "E-mail enviado" : "Link gerado"}</h2>
          <p class="muted" style="margin:8px 0 12px">${r.email_enviado
            ? `Enviamos o link de redefinição para ${r.email}. Você também pode copiá-lo:`
            : "Não conseguimos enviar o e-mail. Envie este link manualmente:"}</p>
          <input class="input" readonly value="${r.link}" aria-label="Link de redefinição">
          <div class="grid2" style="margin-top:12px">
            <button class="btn ghost" data-fechar>Fechar</button>
            <button class="btn" data-act="copiar-link">Copiar link</button>
          </div>`);
      } catch (err) {
        erro.textContent = err.texto; erro.hidden = false;
      }
      btn.disabled = false;
    };
  }

  function mostrarLinkConvite(r) {
    abrirSheet(html`
      <h2 class="title">${r.email_enviado ? "Convite enviado" : "Convite criado"}</h2>
      <p class="muted" style="margin:8px 0 12px">${r.email_enviado
        ? `Enviamos o link para ${r.email}. Você também pode copiá-lo:`
        : "Não conseguimos enviar o e-mail. Envie este link manualmente:"}</p>
      <input class="input" readonly value="${r.link}" aria-label="Link do convite">
      <div class="grid2" style="margin-top:12px">
        <button class="btn ghost" data-fechar>Fechar</button>
        <button class="btn" data-act="copiar-link">Copiar link</button>
      </div>`);
  }


  function instalarHTML() {
    const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
    if (standalone) return "";
    if (state.installEvent) return html`<button class="btn secondary block" data-act="instalar">Instalar aplicativo</button>`;
    if (/iphone|ipad|ipod/i.test(navigator.userAgent)) {
      return html`<div class="card small muted">Para instalar no iPhone: toque em <b>Compartilhar</b> e depois em <b>Adicionar à Tela de Início</b>.</div>`;
    }
    return html`<div class="card small muted">Para instalar, use o menu do navegador e escolha <b>Instalar aplicativo</b> / <b>Adicionar à tela inicial</b>.</div>`;
  }

  /* ===================== Roteador ===================== */
  const ROTAS = [
    [/^\/?$/, () => telaBusca()],
    [/^\/licitacao\/(\d+)$/, (m) => telaDetalhe(m[1])],
    [/^\/login$/, () => telaLogin()],
    [/^\/cadastro$/, (m, q) => telaCadastro(q)],
    [/^\/redefinir-senha$/, (m, q) => telaRedefinirSenha(q)],
    [/^\/alertas$/, () => telaAlertas()],
    [/^\/alertas\/novo$/, () => telaAlertaForm(null, state.rascunhoFiltros)],
    [/^\/alertas\/(\d+)\/editar$/, (m) => telaAlertaForm(m[1])],
    [/^\/alertas\/(\d+)\/resultados$/, (m) => telaResultadosAlerta(m[1])],
    [/^\/notificacoes$/, (m, q) => telaNotificacoes(q)],
    [/^\/conta$/, () => telaConta()],
  ];

  async function rotear() {
    fecharSheet();
    const [path, query = ""] = (location.hash.slice(1) || "/").split("?");
    // App fechado: sem sessão só existem login e cadastro por convite.
    if (!session.get() && !["/login", "/cadastro", "/redefinir-senha"].includes(path)) {
      if (path !== "/") state.next = location.hash;
      location.hash = "#/login";
      return;
    }
    if (session.get() && path === "/login") { location.hash = "#/"; return; }
    for (const [re, fn] of ROTAS) {
      const m = path.match(re);
      if (m) {
        if (path !== "/alertas/novo") state.rascunhoFiltros = null;
        await fn(m, query);
        if (path === "/") window.scrollTo(0, state.scrollBusca || 0);
        else window.scrollTo(0, 0);
        if (session.get()) atualizarBadge();
        return;
      }
    }
    location.hash = "#/";
  }

  /* ===================== Ações (delegação) ===================== */
  const acoes = {
    reload: () => rotear(),
    filtros: () => abrirFiltros(),
    "limpar-filtros": () => { aplicarFiltros({}); fecharSheet(); telaBusca(); },
    mais: () => buscar(false),
    "salvar-alerta": () => {
      state.rascunhoFiltros = { ...state.busca.filtros };
      location.hash = "#/alertas/novo";
    },
    compartilhar: async (el) => {
      const url = location.href, title = view().dataset.titulo || "Licitação";
      if (navigator.share) { try { await navigator.share({ title, url }); } catch { /* cancelado */ } }
      else { try { await navigator.clipboard.writeText(url); toast("Link copiado"); } catch { toast("Não foi possível copiar", true); } }
    },
    "toggle-alerta": async (el) => {
      try { await api(`/alertas/${el.dataset.id}/`, { method: "PATCH", body: { ativo: el.checked } }); toast(el.checked ? "Alerta ativado" : "Alerta pausado"); telaAlertas(); }
      catch (e) { el.checked = !el.checked; toast(e.texto, true); }
    },
    "excluir-alerta": (el) => {
      abrirSheet(html`
        <h2 class="title">Excluir alerta?</h2>
        <p class="muted" style="margin:8px 0 16px">As notificações deste alerta também serão removidas.</p>
        <div class="grid2"><button class="btn ghost" data-fechar>Cancelar</button><button class="btn secondary" id="conf-excluir">Excluir</button></div>`, (s) => {
        $("#conf-excluir", s).onclick = async () => {
          try { await api(`/alertas/${el.dataset.id}/`, { method: "DELETE" }); fecharSheet(); toast("Alerta excluído"); telaAlertas(); }
          catch (e) { toast(e.texto, true); }
        };
      });
    },
    "marcar-todas": async () => {
      try { await api("/notificacoes/marcar-todas-lidas/", { method: "POST" }); toast("Tudo marcado como lido"); rotear(); }
      catch (e) { toast(e.texto, true); }
    },
    "abrir-notif": (el, ev) => {
      // Marca como lida em segundo plano; a navegação do <a> interno segue normal.
      api(`/notificacoes/${el.dataset.id}/`, { method: "PATCH", body: { lida: true } }).then(atualizarBadge).catch(() => {});
    },
    instalar: async () => {
      const ev = state.installEvent;
      if (!ev) return;
      ev.prompt();
      await ev.userChoice;
      state.installEvent = null;
      telaConta();
    },
    "push-ativar": async (el) => {
      el.disabled = true;
      try { await push.ativar(); toast("Notificações ativadas"); } catch (e) { toast(e.texto || e.message || "Não foi possível ativar", true); }
      telaConta();
    },
    "push-desativar": async () => {
      try { await push.desativar(); toast("Notificações desativadas"); } catch (e) { toast(e.message || "Falha ao desativar", true); }
      telaConta();
    },
    "push-testar": async () => {
      const reg = await push.registro();
      reg.showNotification("Busca Licitações", {
        body: "É assim que você será avisado das novas licitações.",
        icon: "/static/app/icon-192.png", badge: "/static/app/icon-192.png", data: { url: "/#/notificacoes" },
      });
    },
    "fontes-recarregar": () => carregarFontes(),
    "sync-agora": async (el) => {
      el.disabled = true;
      try { await api(`/fontes/${el.dataset.id}/sincronizar/`, { method: "POST" }); toast("Sincronização iniciada"); }
      catch (e) { toast(e.texto, true); }
      setTimeout(carregarFontes, 2500);
    },
    "copiar-link": async () => {
      try { await navigator.clipboard.writeText(state.ultimoLink || ""); toast("Link copiado"); }
      catch { toast("Não foi possível copiar", true); }
    },
    "revogar-convite": async (el) => {
      try { await api(`/auth/convites/${el.dataset.id}/`, { method: "DELETE" }); toast("Convite removido"); carregarConvites(); }
      catch (e) { toast(e.texto, true); }
    },
    "sair-cadastro": async (el) => {
      try { await push.desativar(); } catch { /* sem push */ }
      session.clear(); state.user = null;
      telaCadastro(`token=${encodeURIComponent(el.dataset.token)}`);
    },
    sair: async () => {
      try { await push.desativar(); } catch { /* sem push */ }
      session.clear(); state.user = null; state.naoLidas = 0;
      $("#badge-notif").hidden = true;
      if ("clearAppBadge" in navigator) navigator.clearAppBadge().catch(() => {});
      toast("Você saiu da conta");
      location.hash = "#/";
    },
  };

  document.addEventListener("click", (ev) => {
    const el = ev.target.closest("[data-act]");
    if (!el || el.tagName === "INPUT") return;
    const fn = acoes[el.dataset.act];
    if (fn) { if (el.tagName === "BUTTON") ev.preventDefault(); fn(el, ev); }
  });
  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (el.tagName === "INPUT" && el.dataset.act) acoes[el.dataset.act]?.(el, ev);
  });

  $("#btn-back").onclick = () => (history.length > 1 ? history.back() : (location.hash = "#/"));
  window.addEventListener("scroll", () => {
    if ((location.hash || "#/") === "#/" || location.hash === "") state.scrollBusca = window.scrollY;
  }, { passive: true });
  window.addEventListener("hashchange", rotear);

  /* ===================== PWA ===================== */
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    state.installEvent = e;
    if (location.hash === "#/conta") telaConta();
  });
  window.addEventListener("appinstalled", () => { state.installEvent = null; toast("Aplicativo instalado"); });
  const setOnline = () => ($("#offline").hidden = navigator.onLine);
  window.addEventListener("online", () => { setOnline(); atualizarBadge(); });
  window.addEventListener("offline", setOnline);
  setOnline();

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}));
  }

  /* ===================== Início ===================== */
  (async () => {
    await carregarUsuario();
    rotear();
  })();
})();
