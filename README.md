# 🎁 Mi Wishlist

Wishlist personal con vista de galería, filtros por tipo y rango de precio, historial de precios de hasta 2 años y alertas por Telegram cuando algo baja de precio.

## Cómo funciona

| Pieza | Qué hace |
|---|---|
| `site/` | La página (HTML/CSS/JS sin dependencias), publicada con GitHub Pages |
| `site/data/items.json` | **Tu lista.** Aquí viven tus artículos |
| `site/data/history/<id>.json` | Historial de precios de cada artículo (se guardan los últimos 2 años) |
| `site/data/state.json`, `alerts.json` | Los genera el robot: precio actual, mínimos y máximos, y alertas |
| `.github/workflows/track.yml` | Cada 6 horas revisa los precios, guarda el historial y te avisa por Telegram |
| `.github/workflows/add-item.yml` | Agrega artículos desde un formulario de *Issues* (funciona desde el celular) |
| `.github/workflows/pages.yml` | Vuelve a publicar la página cuando cambian los datos |

## Puesta en marcha (una sola vez)

### 1. Activar GitHub Pages
*Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
Después ve a *Actions → Publicar página → Run workflow*. La URL será `https://anasaunche.github.io/wishlist/`.

> ⚠️ **Privacidad:** con una cuenta gratuita, GitHub Pages solo funciona en repos **públicos**. Con GitHub Pro sí puedes publicar desde un repo privado, pero la página queda accesible para quien tenga la URL (no la comparte nadie y le puse `noindex` para que Google no la indexe). El repo —tu código y tus datos— sí se mantiene privado.

### 2. Crear tu bot de Telegram
1. En Telegram, abre **@BotFather**, envía `/newbot` y sigue los pasos. Copia el **token**.
2. Abre un chat con tu bot nuevo y envíale cualquier mensaje (por ejemplo `hola`).
3. Visita `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` y copia el número de `"chat":{"id": ...}`.
4. En GitHub: *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN` = el token
   - `TELEGRAM_CHAT_ID` = el número del chat

### 3. Ajustar la configuración (`site/data/config.json`)
- `currency`: tu moneda por defecto (`USD`, `MXN`, `COP`…).
- `site_url`: la URL de tu página, para que el mensaje de Telegram traiga un enlace al historial.
- `alert_drop_pct`: % mínimo de bajada para avisarte (10 por defecto).
- `price_ranges` y `categories`: los rangos de precio y tipos de producto de los filtros.

### 4. Borrar los ejemplos
Los artículos marcados como **Ejemplo** son solo para que veas cómo se ve. Bórralos de `items.json` (los que tienen `"demo": true`), y borra `site/data/history/demo-*.json` y el contenido de `alerts.json` (déjalo como `[]`).

## Agregar artículos

**Opción A — formulario (recomendado):** *Issues → New issue → ➕ Agregar artículo*. Pega la URL, elige la categoría y, si quieres, un precio objetivo. El robot lo agrega, lee su precio y cierra el issue con un comentario.

**Opción B — a mano:** edita `site/data/items.json`:

```json
{
  "id": "tenis-azules",
  "name": "Tenis azules",
  "url": "https://tienda.com/tenis-azules",
  "category": "zapatos",
  "currency": "USD",
  "target_price": 90,
  "image": "https://... (opcional)",
  "notes": "Talla 7 (opcional)",
  "alert_pct": 15,
  "selector": ".precio-final (opcional, ver abajo)",
  "bought": false,
  "added": "2026-11-16"
}
```

Cuando compres algo, ponle `"bought": true`: deja de revisarse y se oculta (puedes verlo con *Mostrar comprados*).

## ¿Cuándo me llega una alerta?

Solo cuando el precio **baja** respecto a la última revisión y además se cumple alguna de estas condiciones:
- 🎯 llegó a tu **precio objetivo** (o menos),
- 📉 bajó al menos `alert_drop_pct` % (o el `alert_pct` del artículo),
- 🏆 es el **precio más bajo de los últimos 2 años**.

La alerta llega a Telegram y aparece en la campanita 🔔 y en un aviso arriba de la página.

## Si un precio no se lee

El robot busca el precio en los datos estructurados de la página (schema.org, metaetiquetas) y en selectores comunes (Amazon, Mercado Libre, Shopify…). Si una tienda no funciona:
- Agrega un `"selector"` CSS que apunte al precio (clic derecho sobre el precio → *Inspeccionar*).
- Algunas tiendas (sobre todo Amazon) a veces bloquean a los robots de GitHub. En ese caso puedes registrar el precio a mano con el formulario usando el campo **Precio actual**.

## Probar en tu computadora

```bash
pip install -r requirements.txt
python scripts/track.py
cd site && python -m http.server 8000   # abre http://localhost:8000
```
