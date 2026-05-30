# GiftGraph Web

## Purpose
Web service for persistent hosting of interactive graph visualizations. No iframe — graphs are served as unified pages with an integrated toolbar.

## Architecture
- **Storage**: HTML files in `graphs/` + `_index.json` metadata
- **Homepage** `GET /`: lists all graphs with stats
- **Graph page** `GET /view/<gid>`: reads stored HTML, injects toolbar, serves as single page
- **Raw HTML** `GET /graph/<gid>`: serves raw HTML for backward compat
- **API** `POST /api/graphs` / `DELETE /api/graphs/<gid>` / `GET /api/graphs`

## Integration
- Bot uploads via `_upload_to_web()` in `handlers/search.py` → returns `/view/<gid>` URL
- Bot no longer sends HTML files — only web links

## Key files
- `server.py` — Flask app with toolbar injection, templates, API
- `graphs/` — stored `.html` files + `_index.json`
- `manage.sh` — local start/stop/restart
- `../tg_gift_bot/services/visualizer.py` — graph rendering engine
- `../tg_gift_bot/handlers/search.py` — bot integration

## Toolbar injection
`_inject_toolbar()` adds to each graph page:
- Fixed top bar with back button, graph name, meta info
- Copy link button, delete button
- CSS for dark/light theme support
- Pushes graph's native UI down (top: 56px)
- Injects `<title>` tag
