"""Agrega una búsqueda (producto genérico) desde el formulario "Buscar producto"."""
from __future__ import annotations

import os
import sys

from add_item import output
from common import ALERTS_FILE, CONFIG_FILE, fmt_money, load_json, parse_price, save_json, slugify, today
import re
from search import SEARCHES_FILE, SEARCH_STATE_FILE, process_search

FIELDS = {"qué quieres": "query", "nombre": "name", "categoría": "category",
          "precio mínimo": "min_price", "precio máximo": "max_price",
          "precio objetivo": "target_price", "debe incluir": "must_include",
          "excluir": "exclude", "tiendas": "stores", "notas": "notes"}


def parse(body: str) -> dict:
    out = {}
    for block in re.split(r"^###\s+", body, flags=re.M)[1:]:
        label, _, value = block.partition("\n")
        value = value.strip()
        if not value or value == "_No response_":
            continue
        for key, field in FIELDS.items():
            if label.strip().lower().startswith(key):
                out[field] = value
                break
    return out


def main() -> int:
    d = parse(os.environ.get("ISSUE_BODY", ""))
    query = (d.get("query") or "").strip()
    if not query:
        output(ok="false", summary="❌ Falta escribir qué producto quieres buscar.")
        return 1
    cfg = load_json(CONFIG_FILE, {})
    searches = load_json(SEARCHES_FILE, [])
    state = load_json(SEARCH_STATE_FILE, {})
    alerts = load_json(ALERTS_FILE, [])
    if any(s["query"].lower() == query.lower() for s in searches):
        output(ok="false", summary="⚠️ Ya estás buscando eso.")
        return 1

    cat_label = (d.get("category") or "otros").lower()
    category = next((c["id"] for c in cfg.get("categories", [])
                     if c["label"].lower() == cat_label), "otros")
    base = "q-" + slugify(query)
    sid, n, ids = base, 2, {s["id"] for s in searches}
    while sid in ids:
        sid, n = f"{base}-{n}", n + 1

    s = {"id": sid, "query": query, "name": d.get("name") or query, "category": category,
         "currency": cfg.get("currency"), "added": today()}
    for k in ("min_price", "max_price", "target_price"):
        if parse_price(d.get(k)):
            s[k] = parse_price(d[k])
    for k in ("must_include", "exclude", "notes"):
        if d.get(k):
            s[k] = d[k]
    if "[x]" in (d.get("stores") or "").lower():
        s["only_favorite_stores"] = True

    process_search(s, cfg, state, alerts)
    searches.append(s)
    save_json(SEARCHES_FILE, searches)
    save_json(SEARCH_STATE_FILE, state)
    save_json(ALERTS_FILE, alerts)

    st = state.get(sid, {})
    if st.get("price"):
        ch, bv = st["cheapest"], st["best_value"]
        summary = (f"✅ Ahora busco **{s['name']}** todos los días.\n\n"
                   f"Encontré {st['count']} ofertas en {st['stores']} tiendas.\n"
                   f"- 💸 Más barato: **{fmt_money(ch['price'], st['currency'])}** en {ch['store']} — [ver]({ch['link']})\n"
                   f"- ⭐ Mejor calidad-precio: **{fmt_money(bv['price'], st['currency'])}** en {bv['store']} — [ver]({bv['link']})")
    else:
        summary = (f"✅ Búsqueda **{s['name']}** guardada, pero esta vez no obtuve resultados.\n\n"
                   f"Motivo: {st.get('error', 'desconocido')}")
    output(ok="true", id=sid, summary=summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
