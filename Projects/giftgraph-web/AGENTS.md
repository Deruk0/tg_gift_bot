# GiftGraph Web

## Purpose
Web service for persistent hosting of interactive graph visualizations. Receives HTML graphs via API, stores them permanently, and serves them at unique URLs with a rich toolbar.

## Useful files
- `server.py` — Flask web server (API + homepage + graph wrapper)
- `graphs/` — stored graph HTML files + `_index.json`
- `manage.sh` — local start/stop/restart helper
- `../tg_gift_bot/services/visualizer.py` — graph rendering (PyVis + theme shell)
- `../tg_gift_bot/config.py` — bot configuration (MAX_NODES_PER_GRAPH, etc.)

## Architecture
- Flask app on port 5100
- API:
  - `POST /api/graphs` — save a graph (JSON: html, label, nodes, edges, path_length)
  - `DELETE /api/graphs/<gid>` — delete a graph (requires auth when GIFTGRAPH_SECRET set)
- Pages:
  - `GET /` — homepage with all saved graphs
  - `GET /view/<gid>` — full-page graph with toolbar (back, theme, delete)
  - `GET /graph/<gid>` — raw graph HTML (fallback for bot/embed)
  - `GET /health` — status

## Hosting
- Running as a Zo user service: `giftgraph-web`
- Public URL: https://giftgraph-web-szeruko.zocomputer.io
- Service ID: svc_UE8vfck7fBE

## Graph features
- **Always draggable** — physics stays on; drag pulls neighbors
- **Leaf nodes** — endpoint nodes cluster close to parents ("sun" effect, 75% pull)
- **Mutual edges** — when A↔B exchanged gifts, single edge with double arrows
- **Dynamic edges** — smooth curves that stretch/shrink when dragging
- **Degree-based sizing** — more connections = bigger node (start: 44, path: 26+deg×1.2, regular: 20+deg×1.0, anonymous: 14+deg×0.5)
- **Smooth hover** — 2× zoom with glow shadow on hover
- **Parallax** — subtle parallax shift on mouse move
- **Settings panel** — node size, edge thickness, spring length, repulsion, reshuffle (via ⚙ button)
- **Colors**: path = gray (#9ca3af), anonymous = orange (#f97316), regular = purple, start = white/black
- **No freeze** — physics stays on (no "Static"/"Drag" badge)

## Integration with GiftGraph Bot
- Bot uploads graphs after rendering via `_upload_to_web()` in `handlers/search.py`
- Uses `GIFTGRAPH_WEB_URL` from config
- Limit: MAX_NODES_PER_GRAPH = 500

## Editing notes
- Graphs are stored as `.html` files + indexed in `_index.json`
- The raw HTML is served at `/graph/<gid>` (for bot fallback + iframes)
- The wrapped view at `/view/<gid>` injects a toolbar (back, theme, delete)
- Keep the API backward-compatible: POST accepts html, label, nodes, edges, path_length
