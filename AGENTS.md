# GiftGraph Bot

## Purpose
Telegram bot for gift-based social graph visualization.

## Useful files
- `main.py` — entrypoint
- `handlers/` — bot commands and callbacks
- `services/graph.py` — graph building logic
- `services/visualizer.py` — HTML/PyVis rendering
- `services/parser.py` — Telegram gift extraction
- `config.py` — environment and runtime configuration
- `manage.sh` — local start/stop/restart helper
- `HOSTING.md` — running and testing notes
- `README.md` — setup and usage guide

## Important repo policy
- This private repo intentionally tracks stateful runtime files when needed, including `.env`, `userbot.session`, and `giftgraph.db`, so the bot can be restored without reconfiguration.
- Keep logs and cache files out of version control.

## Editing notes
- Preserve compatibility with current bot flow and Telegram userbot session.
- When changing graph UX, keep tree and path modes distinct and readable.
- Prefer small, targeted edits over broad rewrites.
