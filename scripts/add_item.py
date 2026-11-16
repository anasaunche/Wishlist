"""Agrega un artículo a la wishlist a partir de un issue creado con el formulario
"Agregar artículo". Lee el cuerpo del issue de la variable ISSUE_BODY.
Escribe en GITHUB_OUTPUT el id y un resumen para comentar en el issue.
"""
from __future__ import annotations

import os
import re
import sys

from common import (ALERTS_FILE, CONFIG_FILE, ITEMS_FILE, STATE_FILE, fmt_money,
                    load_json, parse_price, save_json, slugify, today)
from track import process_item

FIELDS = {
    "nombre": "name",
    "url": "url",
    "categoría": "category",
    "precio objetivo": "target_price",
    "moneda": "currency",
    "imagen": "image",
    "precio actual": "manual_price",
    "notas": "notes",
}


def parse_issue(body: str) -> dict:
    out = {}
    for block in re.split(r"^###\s+", body, flags=re.M)[1:]:
        label, _, value = block.partition("\n")
        value = value.strip()
        if not value or value == "_No response_":
            continue
        label = label.strip().lower()
        for key, field in FIELDS.items():
            if label.startswith(key):
                out[field] = value
                break
    return out


def output(**kw) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    lines = []
    for k, v in kw.items():
        lines.append(f"{k}<<EOF\n{v}\nEOF")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> int:
    data = parse_issue(os.environ.get("ISSUE_BODY", ""))
    url = data.get("url", "").strip()
    if not re.match(r"^https?://", url):
        output(ok="false", summary="❌ La URL no es válida. Debe empezar con http:// o https://")
        return 1

    cfg = load_json(CONFIG_FILE, {})
    items = load_json(ITEMS_FILE, [])
    state = load_json(STATE_FILE, {})
    alerts = load_json(ALERTS_FILE, [])

    found = next((i for i in items if i["url"] == url), None)
    if found:
        manual = parse_price(data.get("manual_price"))
        if not manual:
            output(ok="false", summary="⚠️ Ese artículo ya está en tu wishlist. "
                   "Si quieres registrar su precio a mano, llena el campo *Precio actual*.")
            return 1
        process_item(found, cfg, state, alerts, manual_price=manual)
        save_json(STATE_FILE, state)
        save_json(ALERTS_FILE, alerts)
        output(ok="true", id=found["id"],
               summary=f"✅ Precio de **{found['name']}** actualizado a **{fmt_money(manual, found.get('currency'))}**.")
        return 0

    categories = {c["id"]: c for c in cfg.get("categories", [])}
    cat_label = data.get("category", "otros").lower()
    category = next((cid for cid, c in categories.items()
                     if c["label"].lower() in cat_label or cid in cat_label), "otros")

    name = data.get("name") or ""
    base = slugify(name or url.split("/")[2])
    item_id, n = base, 2
    existing = {i["id"] for i in items}
    while item_id in existing:
        item_id, n = f"{base}-{n}", n + 1

    currency = (data.get("currency") or cfg.get("currency") or "").split(" ")[0].upper() or None
    item = {"id": item_id, "name": name, "url": url, "category": category,
            "currency": currency, "added": today()}
    if parse_price(data.get("target_price")):
        item["target_price"] = parse_price(data["target_price"])
    if data.get("image", "").startswith("http"):
        item["image"] = data["image"]
    if data.get("notes"):
        item["notes"] = data["notes"]

    process_item(item, cfg, state, alerts, manual_price=parse_price(data.get("manual_price")))
    st = state.get(item_id, {})
    if not item["name"]:
        item["name"] = st.get("title") or item_id

    items.append(item)
    save_json(ITEMS_FILE, items)
    save_json(STATE_FILE, state)
    save_json(ALERTS_FILE, alerts)

    if st.get("price"):
        summary = (f"✅ **{item['name']}** agregado a tu wishlist.\n\n"
                   f"Precio actual: **{fmt_money(st['price'], st.get('currency'))}**. "
                   "Lo revisaré automáticamente y te avisaré por Telegram cuando baje.")
    else:
        summary = (f"✅ **{item['name']}** agregado, pero no pude leer su precio automáticamente.\n\n"
                   f"Motivo: {st.get('error', 'desconocido')}\n\n"
                   "Puedes editar `site/data/items.json` y añadir un `selector` CSS para el precio, "
                   "o crear otro issue con el campo *Precio actual*.")
    output(ok="true", id=item_id, summary=summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
