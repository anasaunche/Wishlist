(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const bust = `?v=${Date.now()}`;
  const getJSON = (p, fallback) => fetch(p + bust).then((r) => (r.ok ? r.json() : fallback)).catch(() => fallback);
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
  };

  let cfg = {}, items = [], state = {}, alerts = [], histories = {};
  const filters = { cats: new Set(), range: null, min: null, max: null, q: "", deals: false, bought: false, sort: "deal" };
  let currentItem = null, currentDays = 730;

  // ---------------------------------------------------------------- formato
  const money = (v, cur) => {
    if (v == null || isNaN(v)) return "—";
    const c = (cur || cfg.currency || "USD").toUpperCase();
    try {
      return new Intl.NumberFormat(cfg.locale || "es-MX", { style: "currency", currency: c, maximumFractionDigits: v % 1 ? 2 : 0 }).format(v);
    } catch { return `$${v}`; }
  };
  const dateFmt = (d, opts = { day: "numeric", month: "short", year: "numeric" }) =>
    new Date(d.length === 10 ? d + "T12:00:00" : d).toLocaleDateString(cfg.locale || "es-MX", opts);
  const ago = (iso) => {
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 3600) return `hace ${Math.max(1, Math.round(s / 60))} min`;
    if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
    return `hace ${Math.round(s / 86400)} d`;
  };
  const host = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; } };
  const cat = (id) => (cfg.categories || []).find((c) => c.id === id) || { id, label: id || "Otros", emoji: "✨" };

  // ---------------------------------------------------------------- modelo
  function view(item) {
    const st = state[item.id] || {};
    const hist = histories[item.id] || [];
    const price = st.price ?? hist.at(-1)?.p ?? null;
    const prices = hist.map((h) => h.p);
    const min = prices.length ? Math.min(...prices) : null;
    const max = prices.length ? Math.max(...prices) : null;
    const avg = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;
    const prev = st.previous ?? (hist.length > 1 ? hist.at(-2).p : null);
    const target = item.target_price ?? null;
    const atBest = price != null && prices.length >= 3 && price <= min * 1.001;
    const atTarget = price != null && target != null && price <= target;
    const dropPct = prev && price < prev ? ((prev - price) / prev) * 100 : 0;
    // 0 = en su mínimo histórico, 1 = en su máximo
    const position = max > min ? (price - min) / (max - min) : 0.5;
    const isDeal = atBest || atTarget || (prices.length >= 3 && position <= 0.15);
    return {
      ...item, st, hist, price, min, max, avg, prev, target, atBest, atTarget, dropPct, position, isDeal,
      name: item.name || st.title || item.id,
      image: item.image || st.image,
      currency: item.currency || st.currency || cfg.currency,
    };
  }

  // ---------------------------------------------------------------- filtros
  function renderFilters() {
    const used = new Set(items.map((i) => i.category || "otros"));
    const cats = (cfg.categories || []).filter((c) => used.has(c.id));
    $("#cat-chips").innerHTML = `<button class="chip ${filters.cats.size ? "" : "on"}" data-cat="">Todo</button>` +
      cats.map((c) => `<button class="chip ${filters.cats.has(c.id) ? "on" : ""}" data-cat="${esc(c.id)}">${c.emoji} ${esc(c.label)}</button>`).join("");
    $("#price-chips").innerHTML = (cfg.price_ranges || []).map((r, i) =>
      `<button class="chip ${filters.range === i ? "on" : ""}" data-range="${i}">${esc(r.label)}</button>`).join("");
  }

  function applyFilters(list) {
    let out = list.filter((v) => {
      if (!filters.bought && v.bought) return false;
      if (filters.cats.size && !filters.cats.has(v.category || "otros")) return false;
      const p = v.price;
      let lo = filters.min, hi = filters.max;
      if (filters.range != null) {
        const r = cfg.price_ranges[filters.range];
        lo = r.min; hi = r.max;
      }
      if ((lo != null || hi != null) && p == null) return false;
      if (lo != null && p < lo) return false;
      if (hi != null && p > hi) return false;
      if (filters.deals && !v.isDeal) return false;
      if (filters.q) {
        const hay = `${v.name} ${cat(v.category).label} ${host(v.url)} ${v.notes || ""}`.toLowerCase();
        if (!hay.includes(filters.q)) return false;
      }
      return true;
    });
    const by = {
      deal: (a, b) => (b.isDeal - a.isDeal) || (a.position - b.position) || (b.dropPct - a.dropPct),
      recent: (a, b) => String(b.added || "").localeCompare(String(a.added || "")),
      "price-asc": (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity),
      "price-desc": (a, b) => (b.price ?? -1) - (a.price ?? -1),
      name: (a, b) => a.name.localeCompare(b.name, "es"),
    }[filters.sort];
    return out.sort(by);
  }

  // ---------------------------------------------------------------- galería
  function sparkline(hist) {
    const pts = hist.slice(-90);
    if (pts.length < 2) return "";
    const ps = pts.map((h) => h.p), lo = Math.min(...ps), hi = Math.max(...ps), span = hi - lo || 1;
    const d = pts.map((h, i) => `${(i / (pts.length - 1)) * 100},${26 - ((h.p - lo) / span) * 24}`).join(" L");
    return `<svg class="spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><path d="M${d}" fill="none" stroke="var(--chart)" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function card(v) {
    const c = cat(v.category);
    const flags = [];
    if (v.demo) flags.push(`<span class="flag flag-demo">Ejemplo</span>`);
    if (v.atTarget) flags.push(`<span class="flag flag-target">🎯 Precio objetivo</span>`);
    if (v.atBest) flags.push(`<span class="flag flag-best">🏆 Mejor precio</span>`);
    else if (v.dropPct >= 1) flags.push(`<span class="flag flag-drop">↓ ${Math.round(v.dropPct)}%</span>`);
    if (v.st.error && v.price == null) flags.push(`<span class="flag flag-err">⚠ Sin precio</span>`);
    if (v.bought) flags.push(`<span class="flag flag-demo">✓ Comprado</span>`);
    const img = v.image
      ? `<img src="${esc(v.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'${c.emoji}'}))">`
      : `<span class="ph">${c.emoji}</span>`;
    return `<button class="card ${v.bought ? "bought" : ""}" data-id="${esc(v.id)}" aria-label="${esc(v.name)}">
      <div class="thumb">${img}<div class="flags">${flags.join("")}</div></div>
      <div class="card-body">
        <div class="tags"><span class="tag">${c.emoji} ${esc(c.label)}</span></div>
        <div class="card-name">${esc(v.name)}</div>
        <div class="card-shop">${esc(host(v.url))}</div>
        ${sparkline(v.hist)}
        <div class="card-foot">
          <span class="price">${money(v.price, v.currency)}</span>
          ${v.prev && v.price < v.prev ? `<span class="price-old">${money(v.prev, v.currency)}</span>` : ""}
        </div>
      </div>
    </button>`;
  }

  function renderSummary(all) {
    const active = all.filter((v) => !v.bought);
    const deals = active.filter((v) => v.isDeal).length;
    const totalNow = active.reduce((s, v) => s + (v.price || 0), 0);
    const totalMax = active.reduce((s, v) => s + (v.max || v.price || 0), 0);
    $("#summary").innerHTML = [
      ["Artículos", active.length],
      ["En buen precio", deals],
      ["Total actual", money(totalNow)],
      ["Ahorro vs. máximos", money(Math.max(0, totalMax - totalNow))],
    ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  }

  function render() {
    const all = items.map(view);
    renderSummary(all);
    renderFilters();
    const list = applyFilters(all);
    $("#grid").innerHTML = list.map(card).join("");
    $("#empty").hidden = list.length > 0;
    $("#count").textContent = `${list.length} de ${all.filter((v) => filters.bought || !v.bought).length} artículos`;
  }

  // ---------------------------------------------------------------- detalle
  function openDetail(id) {
    const item = items.find((i) => i.id === id);
    if (!item) return;
    const v = view(item);
    currentItem = v;
    const c = cat(v.category);
    const media = $(".detail-media");
    media.innerHTML = v.image
      ? `<img src="${esc(v.image)}" alt="" referrerpolicy="no-referrer">`
      : `<span class="ph" style="font-size:96px">${c.emoji}</span>`;
    $("#d-tags").innerHTML = `<span class="tag">${c.emoji} ${esc(c.label)}</span><span class="tag">${esc(host(v.url))}</span>` +
      (v.demo ? `<span class="flag flag-demo">Ejemplo</span>` : "");
    $("#d-name").textContent = v.name;
    $("#d-price").textContent = money(v.price, v.currency);
    $("#d-delta").innerHTML = v.prev && v.price !== v.prev
      ? `<span class="flag ${v.price < v.prev ? "flag-drop" : "flag-err"}">${v.price < v.prev ? "↓" : "↑"} ${Math.abs(((v.price - v.prev) / v.prev) * 100).toFixed(0)}% vs. anterior (${money(v.prev, v.currency)})</span>` : "";

    const vd = $("#d-verdict");
    if (v.price == null) { vd.className = "verdict wait"; vd.textContent = v.st.error || "Aún no tengo precio para este artículo."; }
    else if (v.hist.length < 3) { vd.className = "verdict wait"; vd.textContent = "📈 Juntando historial… en unos días podré decirte si es buen momento."; }
    else if (v.atTarget || v.position <= 0.15) { vd.className = "verdict good"; vd.textContent = v.atBest ? "🏆 Está en su precio más bajo de los últimos 2 años. ¡Buen momento para comprar!" : v.atTarget ? "🎯 Llegó a tu precio objetivo. ¡Buen momento para comprar!" : "✅ Muy cerca de su mínimo histórico. Buen momento para comprar."; }
    else if (v.price <= v.avg) { vd.className = "verdict ok"; vd.textContent = "👍 Por debajo de su precio promedio, aunque ha estado más barato."; }
    else { vd.className = "verdict wait"; vd.textContent = `⏳ Mejor espera: ha llegado a ${money(v.min, v.currency)}.`; }

    const st = v.st;
    const minDate = v.hist.find((h) => h.p === v.min)?.d;
    const maxDate = v.hist.find((h) => h.p === v.max)?.d;
    const rows = [
      ["Mínimo (2 años)", v.min != null ? `${money(v.min, v.currency)} ${minDate ? `<small>${dateFmt(minDate)}</small>` : ""}` : "—"],
      ["Máximo (2 años)", v.max != null ? `${money(v.max, v.currency)} ${maxDate ? `<small>${dateFmt(maxDate)}</small>` : ""}` : "—"],
      ["Promedio", money(v.avg, v.currency)],
      ["Precio objetivo", v.target != null ? money(v.target, v.currency) : "<small>sin definir</small>"],
      ["Agregado", v.added ? dateFmt(v.added) : "—"],
      ["Última revisión", st.checked ? ago(st.checked) : "—"],
    ];
    $("#d-stats").innerHTML = rows.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join("");
    $("#d-notes").textContent = v.notes || "";
    $("#d-buy").href = v.url;

    $("#ranges").querySelectorAll("button").forEach((b) => b.classList.toggle("on", +b.dataset.days === currentDays));
    drawChart();
    const dlg = $("#detail");
    if (!dlg.open) dlg.showModal();
    history.replaceState(null, "", `#item=${encodeURIComponent(id)}`);
  }

  function drawChart() {
    const v = currentItem, box = $("#chart");
    const since = new Date(Date.now() - currentDays * 864e5).toISOString().slice(0, 10);
    const pts = v.hist.filter((h) => h.d >= since);
    if (pts.length < 2) {
      box.innerHTML = `<div class="chart-empty">${pts.length ? "Solo hay un registro en este rango." : "Sin datos en este rango todavía."}<br>El historial se llena automáticamente cada vez que reviso el precio.</div>`;
      return;
    }
    const W = 760, H = 260, P = { l: 64, r: 16, t: 14, b: 28 };
    const t0 = +new Date(pts[0].d), t1 = +new Date(pts.at(-1).d);
    const refs = [v.min, v.target].filter((x) => x != null);
    let lo = Math.min(...pts.map((p) => p.p), ...refs), hi = Math.max(...pts.map((p) => p.p));
    const pad = (hi - lo) * 0.12 || hi * 0.05 || 1;
    lo = Math.max(0, lo - pad); hi += pad;
    const x = (d) => P.l + ((+new Date(d) - t0) / (t1 - t0 || 1)) * (W - P.l - P.r);
    const y = (p) => P.t + (1 - (p - lo) / (hi - lo)) * (H - P.t - P.b);

    // línea escalonada: el precio se mantiene hasta el siguiente cambio
    let d = `M${x(pts[0].d)},${y(pts[0].p)}`;
    for (let i = 1; i < pts.length; i++) d += ` H${x(pts[i].d)} V${y(pts[i].p)}`;
    const area = `${d} V${H - P.b} H${x(pts[0].d)} Z`;

    const ticksY = Array.from({ length: 4 }, (_, i) => lo + ((hi - lo) * i) / 3);
    const nX = Math.min(6, pts.length);
    const ticksX = Array.from({ length: nX }, (_, i) => new Date(t0 + ((t1 - t0) * i) / (nX - 1 || 1)).toISOString().slice(0, 10));
    const xOpts = currentDays <= 90 ? { day: "numeric", month: "short" } : { month: "short", year: "2-digit" };
    const shortMoney = (p) => money(Math.round(p), v.currency);

    const ref = (val, cls, label) => val == null ? "" :
      `<g class="ref ${cls}"><line x1="${P.l}" x2="${W - P.r}" y1="${y(val)}" y2="${y(val)}"/></g>`;

    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Historial de precios de ${esc(v.name)}">
      <g class="axis">
        ${ticksY.map((t) => `<line class="grid-line" x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${shortMoney(t)}</text>`).join("")}
        ${ticksX.map((t) => `<text x="${x(t)}" y="${H - 8}" text-anchor="middle">${dateFmt(t, xOpts)}</text>`).join("")}
      </g>
      <path class="area" d="${area}"/>
      ${ref(v.min, "ref-min")}
      ${ref(v.target, "ref-target")}
      <path class="line" d="${d}"/>
      <line class="hover-line" y1="${P.t}" y2="${H - P.b}" visibility="hidden"/>
      <circle class="dot" r="4.5" visibility="hidden"/>
      <rect x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}" fill="transparent" class="hit"/>
    </svg>
    <div class="tooltip" hidden></div>
    <div class="legend">
      <span><i style="border-color:var(--good)"></i>Mínimo 2 años: ${money(v.min, v.currency)}</span>
      ${v.target != null ? `<span><i style="border-color:var(--accent)"></i>Tu objetivo: ${money(v.target, v.currency)}</span>` : ""}
    </div>`;

    const svg = box.querySelector("svg"), tip = box.querySelector(".tooltip");
    const hl = svg.querySelector(".hover-line"), dot = svg.querySelector(".dot");
    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const cx = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) * (W / r.width);
      const t = t0 + ((cx - P.l) / (W - P.l - P.r)) * (t1 - t0);
      let pt = pts[0];
      for (const p of pts) if (+new Date(p.d) <= t) pt = p;
      const px = Math.min(Math.max(cx, P.l), W - P.r), py = y(pt.p);
      hl.setAttribute("x1", px); hl.setAttribute("x2", px); hl.setAttribute("visibility", "visible");
      dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.style.left = `${(px / W) * r.width}px`;
      tip.style.top = `${(py / H) * r.height}px`;
      tip.textContent = `${money(pt.p, v.currency)} · ${dateFmt(pt.d)}`;
    };
    const leave = () => { hl.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hidden = true; };
    const hit = svg.querySelector(".hit");
    hit.addEventListener("mousemove", move);
    hit.addEventListener("touchmove", move, { passive: true });
    hit.addEventListener("mouseleave", leave);
    hit.addEventListener("touchend", leave);
  }

  // ---------------------------------------------------------------- notificaciones
  const seenKey = "wishlist.seenAlerts";
  const seen = () => new Set(store.get(seenKey, []));
  function markSeen(ids) {
    const s = seen(); ids.forEach((i) => s.add(i));
    store.set(seenKey, [...s].slice(-500));
    renderNotifs();
  }

  function renderNotifs() {
    const s = seen();
    const recent = alerts.filter((a) => items.some((i) => i.id === a.item_id));
    const unread = recent.filter((a) => !s.has(a.id));
    const bc = $("#bell-count");
    bc.hidden = unread.length === 0;
    bc.textContent = unread.length > 9 ? "9+" : unread.length;

    $("#notif-list").innerHTML = recent.length ? recent.slice(0, 60).map((a) => `
      <li><button class="notif ${s.has(a.id) ? "" : "unread"}" data-item="${esc(a.item_id)}" data-alert="${esc(a.id)}">
        <div class="n-name">${esc(a.name)}</div>
        <div class="n-prices"><s>${money(a.old, a.currency)}</s> → <strong>${money(a.new, a.currency)}</strong> (−${a.pct}%)</div>
        <div class="n-meta">${(a.reasons || []).map(esc).join(" · ")}</div>
        <div class="n-meta">${ago(a.date)}</div>
      </button></li>`).join("") : `<li class="notif-empty">Aún no hay bajadas de precio. Te avisaré aquí y por Telegram 🔔</li>`;

    const top = unread[0];
    const banner = $("#banner");
    if (top) {
      banner.hidden = false;
      banner.innerHTML = `<div class="banner">
        <span>🔔</span>
        <div class="grow"><strong>¡${esc(top.name)} bajó de precio!</strong> ${money(top.old, top.currency)} → ${money(top.new, top.currency)} (−${top.pct}%)
        ${unread.length > 1 ? ` <span style="color:var(--muted)">y ${unread.length - 1} más</span>` : ""}</div>
        <button class="link" data-item="${esc(top.item_id)}" data-alert="${esc(top.id)}">Ver</button>
        <button data-dismiss="${esc(top.id)}" aria-label="Descartar">×</button>
      </div>`;
    } else banner.hidden = true;
  }

  // ---------------------------------------------------------------- eventos
  function bind() {
    document.addEventListener("click", (e) => {
      const t = e.target.closest("button, [data-close]");
      if (!t) return;
      if (t.dataset.cat !== undefined) {
        if (!t.dataset.cat) filters.cats.clear();
        else filters.cats.has(t.dataset.cat) ? filters.cats.delete(t.dataset.cat) : filters.cats.add(t.dataset.cat);
        render();
      } else if (t.dataset.range !== undefined) {
        const r = +t.dataset.range;
        filters.range = filters.range === r ? null : r;
        $("#pmin").value = $("#pmax").value = ""; filters.min = filters.max = null;
        render();
      } else if (t.classList.contains("card")) {
        openDetail(t.dataset.id);
      } else if (t.dataset.item) {
        if (t.dataset.alert) markSeen([t.dataset.alert]);
        $("#notifs").close();
        openDetail(t.dataset.item);
      } else if (t.dataset.dismiss) {
        markSeen([t.dataset.dismiss]);
      } else if (t.hasAttribute("data-close")) {
        t.closest("dialog").close();
      } else if (t.dataset.days) {
        currentDays = +t.dataset.days;
        $("#ranges").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === t));
        drawChart();
      }
    });
    $("#bell").addEventListener("click", () => $("#notifs").showModal());
    $("#mark-read").addEventListener("click", () => markSeen(alerts.map((a) => a.id)));
    $("#detail").addEventListener("close", () => history.replaceState(null, "", location.pathname + location.search));
    document.querySelectorAll("dialog").forEach((dlg) =>
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); }));

    $("#search").addEventListener("input", (e) => { filters.q = e.target.value.trim().toLowerCase(); render(); });
    const priceInput = () => {
      const lo = parseFloat($("#pmin").value), hi = parseFloat($("#pmax").value);
      filters.min = isNaN(lo) ? null : lo; filters.max = isNaN(hi) ? null : hi;
      filters.range = null; render();
    };
    $("#pmin").addEventListener("input", priceInput);
    $("#pmax").addEventListener("input", priceInput);
    $("#only-deals").addEventListener("change", (e) => { filters.deals = e.target.checked; render(); });
    $("#show-bought").addEventListener("change", (e) => { filters.bought = e.target.checked; render(); });
    $("#sort").addEventListener("change", (e) => { filters.sort = e.target.value; store.set("wishlist.sort", e.target.value); render(); });
    window.addEventListener("hashchange", openFromHash);
  }

  function openFromHash() {
    const m = location.hash.match(/item=([^&]+)/);
    if (m) openDetail(decodeURIComponent(m[1]));
  }

  // ---------------------------------------------------------------- inicio
  async function init() {
    [cfg, items, state, alerts] = await Promise.all([
      getJSON("data/config.json", {}), getJSON("data/items.json", []),
      getJSON("data/state.json", {}), getJSON("data/alerts.json", []),
    ]);
    document.title = cfg.title || document.title;
    $("#site-title").textContent = cfg.title || "Mi Wishlist";
    filters.sort = store.get("wishlist.sort", "deal");
    $("#sort").value = filters.sort;

    const hs = await Promise.all(items.map((i) => getJSON(`data/history/${encodeURIComponent(i.id)}.json`, [])));
    items.forEach((i, n) => { histories[i.id] = hs[n]; });

    const checks = Object.values(state).map((s) => s.checked).filter(Boolean).sort();
    $("#last-check").textContent = checks.length ? `Precios revisados ${ago(checks.at(-1))} · se actualizan automáticamente cada 6 horas` : "";

    bind();
    render();
    renderNotifs();
    openFromHash();
  }

  init();
})();
