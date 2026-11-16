# 🎁 Mi Wishlist

Wishlist personal con vista de galería, filtros por tipo y rango de precio, historial de precios de hasta 2 años, alertas por Telegram cuando algo baja de precio y **búsqueda diaria en varias tiendas** (Amazon, Walmart, Target, H&M, Forever 21…) con tabla comparativa de calidad-precio.

## Cómo funciona

| Pieza | Qué hace |
|---|---|
| `site/` | La página (HTML/CSS/JS sin dependencias), publicada con GitHub Pages |
| `site/data/items.json` | **Tu lista.** Aquí viven tus artículos |
| `site/data/history/<id>.json` | Historial de precios de cada artículo (se guardan los últimos 2 años) |
| `site/data/state.json`, `alerts.json` | Los genera el robot: precio actual, mínimos y máximos, y alertas |
| `.github/workflows/track.yml` | Cada 6 horas revisa los precios, guarda el historial y te avisa por Telegram |
| `.github/workflows/search.yml` | Una vez al día busca tus productos genéricos en Google Shopping (todas las tiendas) |
| `.github/workflows/add-item.yml` | Agrega artículos o búsquedas desde formularios de *Issues* (funciona desde el celular) |
| `site/data/searches.json` | Tus búsquedas genéricas ("leather jacket", "iPad Pro"…) |
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

### 3. Clave para buscar en tiendas
Las búsquedas usan Google Shopping, que junta ofertas de Amazon, Walmart, Target, H&M, Forever 21, Best Buy y cientos de tiendas más (las tiendas bloquean a los robots si se les consulta directo). Necesitas **una** de estas claves gratuitas:

| Servicio | Gratis | Secret en GitHub |
|---|---|---|
| [SerpApi](https://serpapi.com) (recomendado) | ~250 búsquedas al mes → ~8 productos revisados a diario | `SERPAPI_KEY` |
| [Serper.dev](https://serper.dev) | 2,500 búsquedas una sola vez | `SERPER_API_KEY` |

Cada producto buscado gasta **1 búsqueda al día**. Agrégala en *Settings → Secrets and variables → Actions*.

### 4. Ajustar la configuración (`site/data/config.json`)
- `currency`: tu moneda por defecto (`USD`, `MXN`, `COP`…).
- `site_url`: la URL de tu página, para que el mensaje de Telegram traiga un enlace al historial.
- `alert_drop_pct`: % mínimo de bajada para avisarte (10 por defecto).
- `stores`: tus tiendas favoritas (se marcan con ♥ y puedes filtrar solo por ellas). `only_favorite_stores: true` ignora todas las demás.
- `search_country`: país de la búsqueda (`us`, `mx`, `co`…) y `search_language`.
- `price_ranges` y `categories`: los rangos de precio y tipos de producto de los filtros.

### 5. Borrar los ejemplos
Los artículos marcados como **Ejemplo** son solo para que veas cómo se ve. Bórralos de `items.json` y `searches.json` (los que tienen `"demo": true`), y borra `site/data/history/demo-*.json`, `site/data/history/q-demo-*.json`, `site/data/search_results/q-demo-*.json`, `search_state.json` (déjalo como `{}`) y el contenido de `alerts.json` (déjalo como `[]`).

## Buscar un producto en varias tiendas

*Issues → New issue → 🔍 Buscar producto en varias tiendas* (o el botón **+ Agregar** de la página). Escribe lo que quieres, p. ej. `women's leather jacket` o `ipad pro 11 m4`.

Cada día el robot busca ese producto y en la página verás:
- **💸 Más barato en …**: botón directo a la oferta más barata.
- **⭐ Mejor calidad-precio**: la oferta con mejor equilibrio entre precio y calificación.
- **Tabla comparativa** con todas las tiendas: precio, precio anterior, estrellas, número de reseñas y puntaje calidad-precio (0–100). Puedes ordenar por cualquier columna y filtrar por tienda o solo favoritas.
- **+ Seguir**: si te decides por una oferta concreta, la agrega como artículo para seguir su precio exacto.
- Gráfica del **precio más bajo encontrado** día a día, y alerta en Telegram cuando baja.

**Cómo se calcula el puntaje calidad-precio:** 50% precio (100 = el más barato de la lista) + 50% calidad. La calidad usa la calificación con un ajuste bayesiano: un producto con 4.9★ y 5 reseñas no le gana a uno con 4.7★ y 3,000 reseñas.

**Tips para buenos resultados:** usa *Precio mínimo* y *Excluir palabras* (`case, cover, refurbished`) para quitar accesorios, y *Debe incluir* (`ipad pro 11`) para exigir palabras en el título. Además, se descartan solos los precios menores al 25% de la mediana.

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
