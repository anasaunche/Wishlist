"""Búsquedas diarias: para cada producto de `searches.json` (p. ej. "chamarra de piel")
consulta Google Shopping, que reúne ofertas de Amazon, Target, Walmart, H&M, Forever 21
y muchas tiendas más. Guarda la tabla comparativa, el historial del mejor precio y avisa
por Telegram cuando el precio más bajo encontrado baja.

Proveedores (usa el que tenga clave en los secrets de GitHub):
    SERPAPI_KEY      -> https://serpapi.com      (≈250 búsquedas gratis al mes)
    SERPER_API_KEY   -> https://serper.dev       (2,500 búsquedas gratis, una vez)

Uso:
    python scripts/search.py            # todas las búsquedas
    python scripts/search.py <id> [...] # solo esas
"""
from __future__ import annotations

import html
import os
import re
import statistics
import sys
import time

import requests

from common import (ALERTS_FILE, CONFIG_FILE, DATA, MAX_ALERTS, fmt_money, load_history,
                    load_json, now_iso, parse_price, save_history, save_json, send_telegram,
                    today)
from track import detect_drop, summarize

SEARCHES_FILE = DATA / "searches.json"
SEARCH_STATE_FILE = DATA / "search_state.json"
RESULTS_DIR = DATA / "search_results"


# ---------------------------------------------------------------- proveedores

def _serpapi(query: str, cfg: dict) -> list[dict]:
    r = requests.get("https://serpapi.com/search.json", params={
        "engine": "google_shopping", "q": query,
        "gl": cfg.get("search_country", "us"), "hl": cfg.get("search_language", "en"),
        "num": 60, "api_key": os.environ["SERPAPI_KEY"],
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    rows = data.get("shopping_results", []) + data.get("inline_shopping_results", [])
    return [{
        "title": o.get("title"),
        "store": o.get("source"),
        "price": o.get("extracted_price") or parse_price(o.get("price")),
        "old_price": o.get("extracted_old_price"),
        "rating": o.get("rating"),
        "reviews": o.get("reviews"),
        "link": o.get("link") or o.get("product_link"),
        "image": o.get("thumbnail"),
        "delivery": o.get("delivery"),
    } for o in rows]


def _serper(query: str, cfg: dict) -> list[dict]:
    r = requests.post("https://google.serper.dev/shopping", json={
        "q": query, "gl": cfg.get("search_country", "us"), "hl": cfg.get("search_language", "en"),
        "num": 60,
    }, headers={"X-API-KEY": os.environ["SERPER_API_KEY"]}, timeout=60)
    r.raise_for_status()
    return [{
        "title": o.get("title"),
        "store": o.get("source"),
        "price": parse_price(o.get("price")),
        "rating": o.get("rating"),
        "reviews": o.get("ratingCount"),
        "link": o.get("link"),
        "image": o.get("imageUrl"),
        "delivery": o.get("delivery"),
    } for o in r.json().get("shopping", [])]


def provider_search(query: str, cfg: dict) -> list[dict]:
    choice = cfg.get("search_provider", "auto")
    if choice in ("auto", "serpapi") and os.environ.get("SERPAPI_KEY"):
        return _serpapi(query, cfg)
    if choice in ("auto", "serper") and os.environ.get("SERPER_API_KEY"):
        return _serper(query, cfg)
    raise RuntimeError("Falta la clave de búsqueda: agrega el secret SERPAPI_KEY o SERPER_API_KEY.")


# ---------------------------------------------------------------- limpieza y puntaje

def _norm(s: str) -> str:
    s = (s or "").lower()
    for a, b in zip("áéíóúüñ", "aeiouun"):
        s = s.replace(a, b)
    return s


def store_key(store: str, cfg: dict) -> str | None:
    """Devuelve el id de la tienda favorita si coincide (amazon, target, ...)."""
    name = _norm(store)
    for st in cfg.get("stores", []):
        if any(_norm(m) in name for m in st.get("match", [st["label"]])):
            return st["id"]
    return None


def clean_offers(raw: list[dict], search: dict, cfg: dict) -> list[dict]:
    words = [w for w in re.split(r"\s+", _norm(search.get("must_include") or "")) if w]
    exclude = [_norm(w.strip()) for w in re.split(r"[,;\n]", search.get("exclude") or "") if w.strip()]
    lo, hi = search.get("min_price"), search.get("max_price")
    seen, out = set(), []
    for o in raw:
        p = o.get("price")
        if not p or not o.get("title") or not o.get("link"):
            continue
        t = _norm(o["title"])
        if words and not all(w in t for w in words):
            continue
        if any(x and x in t for x in exclude):
            continue
        if (lo and p < lo) or (hi and p > hi):
            continue
        key = (_norm(o.get("store")), t[:60], round(p, 2))
        if key in seen:
            continue
        seen.add(key)
        o["store"] = o.get("store") or "Tienda"
        o["store_id"] = store_key(o["store"], cfg)
        o["rating"] = float(o["rating"]) if o.get("rating") else None
        o["reviews"] = int(re.sub(r"\D", "", str(o["reviews"])) or 0) if o.get("reviews") else 0
        out.append(o)

    if search.get("only_favorite_stores") or cfg.get("only_favorite_stores"):
        out = [o for o in out if o["store_id"]]

    # Descarta precios absurdamente bajos (fundas, repuestos, accesorios): < 25% de la mediana
    if len(out) >= 5:
        med = statistics.median(o["price"] for o in out)
        out = [o for o in out if o["price"] >= med * 0.25]
    return out


def score_offers(offers: list[dict]) -> None:
    """Puntaje calidad-precio de 0 a 100.

    - Precio: 100 el más barato, 0 el más caro.
    - Calidad: calificación bayesiana: con pocas reseñas se acerca a 3.8★ (escéptico),
      con muchas pesa la calificación real. 3.5★ o menos = 0, 5★ = 100.
      Sin calificación cuenta como 3.8★.
    """
    if not offers:
        return
    prices = [o["price"] for o in offers]
    pmin, pmax = min(prices), max(prices)
    prior, m = 3.8, 30  # 30 reseñas "virtuales" de 3.8★
    for o in offers:
        price_s = 1 - (o["price"] - pmin) / (pmax - pmin) if pmax > pmin else 1
        v = o["reviews"] or 0 if o["rating"] else 0
        bayes = ((o["rating"] or prior) * v + prior * m) / (v + m)
        o["quality"] = round(max(0.0, min(1.0, (bayes - 3.5) / 1.5)) * 100)
        o["score"] = round((0.5 * price_s + 0.5 * o["quality"] / 100) * 100)


# ---------------------------------------------------------------- proceso

def process_search(search: dict, cfg: dict, state: dict, alerts: list[dict],
                   raw: list[dict] | None = None) -> None:
    sid = search["id"]
    st = state.setdefault(sid, {})
    print(f"🔍 {search['query']}")
    st["checked"] = now_iso()
    try:
        raw = raw if raw is not None else provider_search(search["query"], cfg)
    except Exception as e:  # noqa: BLE001
        st["error"] = str(e)[:300]
        print(f"  ! {st['error']}")
        return

    offers = clean_offers(raw, search, cfg)
    score_offers(offers)
    offers.sort(key=lambda o: o["price"])
    if not offers:
        st["error"] = "No encontré ofertas que coincidan. Revisa las palabras excluidas o el rango de precio."
        st["count"] = 0
        save_json(RESULTS_DIR / f"{sid}.json", {"query": search["query"], "checked": st["checked"], "offers": []})
        print(f"  ! {st['error']}")
        return
    st.pop("error", None)

    cheapest = offers[0]
    best_value = max(offers, key=lambda o: (o["score"], -o["price"]))
    currency = search.get("currency") or cfg.get("currency")
    save_json(RESULTS_DIR / f"{sid}.json", {
        "query": search["query"], "checked": st["checked"], "currency": currency, "offers": offers[:60],
    })

    history = load_history(sid)
    price = cheapest["price"]
    item_like = {**search, "currency": currency, "name": search.get("name") or search["query"]}
    reasons = detect_drop(item_like, history, price, cfg)
    previous = [h for h in history if h["d"] < today()]
    last = previous[-1]["p"] if previous else None
    history = previous + [{"d": today(), "p": price}]
    save_history(sid, history)

    st.update({
        "price": price, "currency": currency, "previous": last, "count": len(offers),
        "stores": len({o["store"] for o in offers}),
        "cheapest": {k: cheapest.get(k) for k in ("title", "store", "price", "link", "image", "rating", "reviews")},
        "best_value": {k: best_value.get(k) for k in ("title", "store", "price", "link", "image", "rating", "reviews", "score")},
        "image": cheapest.get("image") or best_value.get("image"),
        **summarize(history),
    })
    print(f"  {len(offers)} ofertas · más barato: {fmt_money(price, currency)} en {cheapest['store']}")

    if reasons:
        pct = round((last - price) / last * 100, 1)
        name = item_like["name"]
        alert = {
            "id": f"{sid}-{int(time.time())}", "item_id": sid, "name": name, "date": now_iso(),
            "old": last, "new": price, "pct": pct, "currency": currency,
            "reasons": reasons + [f"🏪 En {cheapest['store']}"], "url": cheapest["link"],
        }
        alerts.insert(0, alert)
        del alerts[MAX_ALERTS:]
        site = cfg.get("site_url")
        send_telegram(
            f"🔔 <b>¡Encontré {html.escape(name)} más barato!</b>\n\n"
            f"{html.escape(cheapest['title'])}\n"
            f"{fmt_money(last, currency)} ➜ <b>{fmt_money(price, currency)}</b> (−{pct:g}%) en "
            f"<b>{html.escape(cheapest['store'])}</b>\n\n"
            + "\n".join(html.escape(r) for r in reasons)
            + f"\n\n🛒 <a href=\"{html.escape(cheapest['link'])}\">Ver oferta</a>"
            + (f"\n📊 <a href=\"{html.escape(site)}#item={sid}\">Comparar tiendas</a>" if site else "")
        )


def main(ids: list[str]) -> None:
    cfg = load_json(CONFIG_FILE, {})
    searches = load_json(SEARCHES_FILE, [])
    state = load_json(SEARCH_STATE_FILE, {})
    alerts = load_json(ALERTS_FILE, [])
    for s in searches:
        if (ids and s["id"] not in ids) or s.get("bought") or s.get("demo"):
            continue
        process_search(s, cfg, state, alerts)
        time.sleep(1)
    valid = {s["id"] for s in searches}
    save_json(SEARCH_STATE_FILE, {k: v for k, v in state.items() if k in valid})
    save_json(ALERTS_FILE, alerts)


if __name__ == "__main__":
    main(sys.argv[1:])
