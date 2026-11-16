"""Utilidades compartidas: rutas, lectura/escritura de datos, scraping de precios y Telegram."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
HISTORY_DIR = DATA / "history"
ITEMS_FILE = DATA / "items.json"
STATE_FILE = DATA / "state.json"
ALERTS_FILE = DATA / "alerts.json"
CONFIG_FILE = DATA / "config.json"

HISTORY_DAYS = 730  # 2 años
MAX_ALERTS = 200

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


# ---------------------------------------------------------------- datos

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def today() -> str:
    return dt.date.today().isoformat()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    text = text.lower()
    for a, b in zip("áéíóúüñ", "aeiouun"):
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:50] or "articulo"


def history_path(item_id: str) -> Path:
    return HISTORY_DIR / f"{item_id}.json"


def load_history(item_id: str) -> list[dict]:
    return load_json(history_path(item_id), [])


def save_history(item_id: str, history: list[dict]) -> None:
    cutoff = (dt.date.today() - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    history = sorted((h for h in history if h["d"] >= cutoff), key=lambda h: h["d"])
    save_json(history_path(item_id), history)


# ---------------------------------------------------------------- precios

def parse_price(raw) -> float | None:
    """Convierte '$1.299,99', '1,299.99', 'MX$ 12,999', 1299 -> float."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    s = re.sub(r"[^\d.,]", "", str(raw))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        # varios separadores o grupos de 3 dígitos => separador de miles
        if len(parts) > 2 or len(parts[-1]) == 3:
            s = s.replace(sep, "")
        else:
            s = s.replace(sep, ".")
    try:
        value = float(s)
    except ValueError:
        return None
    return value if value > 0 else None


def _walk_jsonld(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk_jsonld(n)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk_jsonld(node[key])


def _from_jsonld(soup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" not in types and "ProductGroup" not in types:
                continue
            offers = node.get("offers") or {}
            offers = offers if isinstance(offers, list) else [offers]
            prices = []
            currency = None
            for off in offers:
                if not isinstance(off, dict):
                    continue
                p = parse_price(off.get("price") or off.get("lowPrice"))
                if p is None and isinstance(off.get("priceSpecification"), dict):
                    p = parse_price(off["priceSpecification"].get("price"))
                if p:
                    prices.append(p)
                    currency = currency or off.get("priceCurrency")
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            if prices:
                return {
                    "price": min(prices),
                    "currency": currency,
                    "title": node.get("name"),
                    "image": image,
                }
    return {}


def _meta(soup, *names):
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) \
            or soup.find("meta", attrs={"itemprop": n})
        if tag and tag.get("content"):
            return tag["content"]
    return None


PRICE_SELECTORS = [
    # Amazon
    "#corePrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    "#priceblock_dealprice", "#priceblock_ourprice", "#price_inside_buybox",
    ".a-price .a-offscreen",
    # Mercado Libre
    ".ui-pdp-price__second-line .andes-money-amount__fraction",
    # Shopify y genéricos
    "[itemprop=price]", ".price ins .amount", ".product-price", ".price",
]


def extract(html: str, url: str, selector: str | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    info = _from_jsonld(soup)

    if selector:
        el = soup.select_one(selector)
        if el:
            p = parse_price(el.get("content") or el.get_text(" ", strip=True))
            if p:
                info["price"] = p

    if not info.get("price"):
        p = parse_price(_meta(soup, "product:price:amount", "og:price:amount", "price"))
        if p:
            info["price"] = p
            info["currency"] = _meta(soup, "product:price:currency", "og:price:currency", "priceCurrency")

    if not info.get("price"):
        for sel in PRICE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                p = parse_price(el.get("content") or el.get_text(" ", strip=True))
                if p:
                    info["price"] = p
                    break

    info.setdefault("title", _meta(soup, "og:title", "twitter:title")
                    or (soup.title.string.strip() if soup.title and soup.title.string else None))
    if not info.get("image"):
        info["image"] = _meta(soup, "og:image", "twitter:image")
    if info.get("image"):
        info["image"] = urljoin(url, info["image"])
    return info


def fetch_product(url: str, selector: str | None = None) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return extract(resp.text, url, selector)


# ---------------------------------------------------------------- telegram

def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("  (Telegram no configurado: falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID)")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": False},
            timeout=20,
        )
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  ! Error enviando a Telegram: {e}")
        return False


def fmt_money(value: float, currency: str | None) -> str:
    cur = (currency or "").upper()
    txt = f"{value:,.2f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"
    return f"{cur} ${txt}".strip() if cur else f"${txt}"
