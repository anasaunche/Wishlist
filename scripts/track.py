"""Revisa el precio de cada artículo, guarda el historial (2 años) y envía alertas.

Uso:
    python scripts/track.py              # todos los artículos
    python scripts/track.py <id> [...]   # solo esos artículos
"""
from __future__ import annotations

import html
import statistics
import sys
import time

from common import (ALERTS_FILE, CONFIG_FILE, ITEMS_FILE, MAX_ALERTS, STATE_FILE,
                    fetch_product, fmt_money, load_history, load_json, now_iso,
                    save_history, save_json, send_telegram, today)


def detect_drop(item: dict, history: list[dict], price: float, cfg: dict) -> list[str]:
    """Devuelve las razones de alerta (lista vacía = sin alerta).

    Solo alerta cuando el precio BAJA respecto al último registrado, así no se repiten
    mensajes mientras el precio se mantiene.
    """
    previous = [h for h in history if h["d"] < today()]
    if not previous:
        return []
    last = previous[-1]["p"]
    if price >= last:
        return []

    reasons = []
    drop_pct = (last - price) / last * 100
    threshold = float(item.get("alert_pct") or cfg.get("alert_drop_pct", 10))
    target = item.get("target_price")

    if target and price <= float(target) < last:
        reasons.append(f"🎯 Llegó a tu precio objetivo ({fmt_money(float(target), item.get('currency'))})")
    if drop_pct >= threshold:
        reasons.append(f"📉 Bajó {drop_pct:.0f}% desde el último precio")
    lowest = min(h["p"] for h in previous)
    if len(previous) >= 3 and price < lowest:
        reasons.append("🏆 Precio más bajo de los últimos 2 años")
    return reasons


def summarize(history: list[dict]) -> dict:
    prices = [h["p"] for h in history]
    if not prices:
        return {}
    lo = min(history, key=lambda h: h["p"])
    hi = max(history, key=lambda h: h["p"])
    return {
        "min": lo["p"], "min_date": lo["d"],
        "max": hi["p"], "max_date": hi["d"],
        "avg": round(statistics.mean(prices), 2),
        "points": len(prices),
    }


def process_item(item: dict, cfg: dict, state: dict, alerts: list[dict],
                 manual_price: float | None = None) -> None:
    item_id = item["id"]
    st = state.setdefault(item_id, {})
    history = load_history(item_id)
    print(f"• {item.get('name', item_id)}")

    info = {}
    if manual_price:
        info = {"price": manual_price}
    else:
        try:
            info = fetch_product(item["url"], item.get("selector"))
        except Exception as e:  # noqa: BLE001
            st["error"] = f"No se pudo abrir la página: {e}"[:300]
            st["checked"] = now_iso()
            print(f"  ! {st['error']}")
            return

    # metadatos que ayudan a la galería si el usuario no los puso
    if info.get("title"):
        st["title"] = info["title"][:200]
    if info.get("image"):
        st["image"] = info["image"]

    price = info.get("price")
    st["checked"] = now_iso()
    if not price:
        st["error"] = "No encontré el precio en la página (prueba agregando un 'selector' CSS)."
        print(f"  ! {st['error']}")
        return
    st.pop("error", None)

    currency = item.get("currency") or info.get("currency") or cfg.get("currency")
    reasons = detect_drop(item, history, price, cfg)

    previous = [h for h in history if h["d"] < today()]
    last = previous[-1]["p"] if previous else None
    history = previous + [{"d": today(), "p": price}]
    save_history(item_id, history)

    st.update({"price": price, "currency": currency, "previous": last, **summarize(history)})
    print(f"  precio: {fmt_money(price, currency)}" + (f" (antes {fmt_money(last, currency)})" if last else ""))

    if reasons:
        pct = round((last - price) / last * 100, 1)
        alert = {
            "id": f"{item_id}-{int(time.time())}",
            "item_id": item_id,
            "name": item.get("name") or st.get("title") or item_id,
            "date": now_iso(),
            "old": last, "new": price, "pct": pct,
            "currency": currency,
            "reasons": reasons,
            "url": item["url"],
        }
        alerts.insert(0, alert)
        del alerts[MAX_ALERTS:]
        st["last_alert"] = alert["date"]
        print("  ¡ALERTA!", "; ".join(reasons))
        site = cfg.get("site_url")
        msg = (
            f"🔔 <b>¡Bajó de precio!</b>\n\n"
            f"<b>{html.escape(alert['name'])}</b>\n"
            f"{fmt_money(last, currency)} ➜ <b>{fmt_money(price, currency)}</b> (−{pct:g}%)\n\n"
            + "\n".join(html.escape(r) for r in reasons)
            + f"\n\n🛒 <a href=\"{html.escape(item['url'])}\">Ver en la tienda</a>"
            + (f"\n📊 <a href=\"{html.escape(site)}#item={item_id}\">Ver historial</a>" if site else "")
        )
        send_telegram(msg)


def main(ids: list[str]) -> None:
    cfg = load_json(CONFIG_FILE, {})
    items = load_json(ITEMS_FILE, [])
    state = load_json(STATE_FILE, {})
    alerts = load_json(ALERTS_FILE, [])

    for item in items:
        if ids and item["id"] not in ids:
            continue
        if item.get("bought") or item.get("demo"):
            continue
        process_item(item, cfg, state, alerts)
        time.sleep(2)  # ser amables con las tiendas

    # limpia estado de artículos eliminados
    valid = {i["id"] for i in items}
    state = {k: v for k, v in state.items() if k in valid}
    save_json(STATE_FILE, state)
    save_json(ALERTS_FILE, alerts)


if __name__ == "__main__":
    main(sys.argv[1:])
