"""
GiftGraph Web — сервис для постоянного хостинга интерактивных графов.
"""

import json
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string, request, send_from_directory, abort

app = Flask(__name__)

GRAPHS_DIR = os.path.join(os.path.dirname(__file__), "graphs")
INDEX_PATH = os.path.join(GRAPHS_DIR, "_index.json")
API_SECRET = os.getenv("GIFTGRAPH_SECRET", "").strip()

os.makedirs(GRAPHS_DIR, exist_ok=True)

# ── Индекс ────────────────────────────────────────────────────────────────

def _load_index() -> dict:
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"graphs": {}}

def _save_index(idx: dict) -> None:
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

def _api_key_ok() -> bool:
    if not API_SECRET:
        return True
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {API_SECRET}"

# ── Главная ───────────────────────────────────────────────────────────────

HOME_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GiftGraph Web</title>
<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
    background: #050816;
    color: #e5e7eb;
    min-height: 100vh;
    overflow-x: hidden;
  }
  .bg-glow {
    position: fixed; inset: 0;
    background: radial-gradient(ellipse at 20% 20%, rgba(124,58,237,0.10), transparent 50%),
                radial-gradient(ellipse at 80% 70%, rgba(59,130,246,0.08), transparent 40%);
    pointer-events: none; z-index: 0;
  }
  .container { max-width: 800px; margin: 0 auto; padding: 3rem 1.5rem; position: relative; z-index: 1; }

  header { text-align: center; margin-bottom: 3rem; }
  header h1 { font-size: 2.25rem; font-weight: 800; letter-spacing: -0.03em; background: linear-gradient(135deg, #c4b5fd, #7c3aed, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
  header p { color: #94a3b8; font-size: 0.95rem; margin-top: 0.5rem; }

  .stats { display: flex; gap: 1rem; justify-content: center; margin-bottom: 2.5rem; flex-wrap: wrap; }
  .stat { background: rgba(10,14,30,0.60); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 0.75rem 1.25rem; text-align: center; min-width: 80px; backdrop-filter: blur(12px); }
  .stat .num { font-size: 1.5rem; font-weight: 700; color: #c4b5fd; }
  .stat .lbl { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }

  .graphs-list { display: flex; flex-direction: column; gap: 0.75rem; }
  .graph-card {
    background: rgba(10,14,30,0.55); border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px; padding: 1rem 1.25rem;
    display: flex; justify-content: space-between; align-items: center;
    transition: border-color 0.2s, background 0.2s, transform 0.15s;
    backdrop-filter: blur(10px); gap: 1rem;
  }
  .graph-card:hover { border-color: rgba(124,58,237,0.35); background: rgba(10,14,30,0.70); transform: translateY(-1px); }
  .graph-card .info { min-width: 0; flex: 1; }
  .graph-card .info a {
    color: #c4b5fd; text-decoration: none; font-weight: 600; font-size: 0.95rem;
    word-break: break-word; transition: color 0.15s;
  }
  .graph-card .info a:hover { color: #ddd6fe; }
  .graph-meta { color: #64748b; font-size: 0.75rem; margin-top: 0.2rem; display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .graph-meta span { white-space: nowrap; }

  .graph-actions { display: flex; gap: 0.5rem; align-items: center; flex-shrink: 0; }
  .btn {
    border: 1px solid rgba(255,255,255,0.10); border-radius: 10px;
    padding: 0.45rem 0.8rem; font-size: 0.8rem; font-weight: 600;
    cursor: pointer; transition: all 0.15s;
    text-decoration: none; display: inline-flex; align-items: center; gap: 0.3rem;
    background: rgba(255,255,255,0.06); color: #94a3b8;
    white-space: nowrap;
  }
  .btn:hover { background: rgba(255,255,255,0.12); color: #e5e7eb; }
  .btn.danger { color: #f87171; border-color: rgba(248,113,113,0.25); }
  .btn.danger:hover { background: rgba(248,113,113,0.12); color: #fca5a5; border-color: rgba(248,113,113,0.4); }
  .btn.open { background: rgba(124,58,237,0.15); border-color: rgba(124,58,237,0.3); color: #c4b5fd; }
  .btn.open:hover { background: rgba(124,58,237,0.25); }

  .empty { text-align: center; padding: 4rem 0; color: #64748b; }
  .empty .icon { font-size: 3rem; margin-bottom: 1rem; opacity: 0.4; }
  .empty p { font-size: 0.95rem; line-height: 1.6; }
  .empty code { background: rgba(255,255,255,0.06); padding: 0.15rem 0.5rem; border-radius: 5px; font-size: 0.85rem; color: #a78bfa; }

  .toast {
    position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%);
    background: rgba(10,14,30,0.92); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px; padding: 0.75rem 1.5rem; color: #e5e7eb; font-size: 0.85rem;
    z-index: 999; backdrop-filter: blur(14px); opacity: 0; pointer-events: none;
    transition: opacity 0.25s; box-shadow: 0 12px 40px rgba(0,0,0,0.3);
  }
  .toast.show { opacity: 1; }
  .toast.error { border-color: rgba(248,113,113,0.35); }

  footer { text-align: center; color: #475569; font-size: 0.7rem; margin-top: 3rem; padding-bottom: 2rem; }

  @media (max-width: 540px) {
    .graph-card { flex-direction: column; align-items: flex-start; }
    .graph-actions { align-self: flex-end; }
  }
</style>
</head>
<body>
<div class="bg-glow"></div>
<div class="container">
  <header>
    <h1>🕸 GiftGraph Web</h1>
    <p>Интерактивные графы социальных связей Telegram</p>
  </header>

  {% if graphs %}
  <div class="stats">
    <div class="stat"><div class="num">{{ total_nodes }}</div><div class="lbl">Узлов</div></div>
    <div class="stat"><div class="num">{{ total_edges }}</div><div class="lbl">Рёбер</div></div>
    <div class="stat"><div class="num">{{ graphs|length }}</div><div class="lbl">Графов</div></div>
  </div>
  {% endif %}

  <div class="graphs-list">
  {% if graphs %}
    {% for gid, info in graphs.items() %}
    <div class="graph-card" id="card-{{ gid }}">
      <div class="info">
        <a href="/view/{{ gid }}">{{ info.get("label", gid) }}</a>
        <div class="graph-meta">
          <span>🟣 {{ info.get("nodes", "?") }} узлов</span>
          <span>🔗 {{ info.get("edges", "?") }} рёбер</span>
          <span>🕐 {{ info.get("created", "") }}</span>
          {% if info.get("path_length") %}<span>📍 путь {{ info.path_length }} шаг.</span>{% endif %}
        </div>
      </div>
      <div class="graph-actions">
        <a href="/view/{{ gid }}" class="btn open">📂 Открыть</a>
        <button class="btn danger" onclick="deleteGraph('{{ gid }}', this)">🗑</button>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">
      <div class="icon">🕸</div>
      <p>Пока нет сохранённых графов.<br>Используйте <code>/search</code> в Telegram-боте, чтобы создать первый.</p>
    </div>
  {% endif %}
  </div>

  <footer>GiftGraph Web · графы хранятся постоянно</footer>
</div>

<div id="toast" class="toast"></div>

<script>
function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.className = 'toast'; }, 2500);
}

async function deleteGraph(gid, btn) {
  if (!confirm('Удалить этот граф? Действие необратимо.')) return;
  btn.disabled = true;
  btn.textContent = '...';
  try {
    const r = await fetch('/api/graphs/' + gid, { method: 'DELETE' });
    if (r.ok) {
      const card = document.getElementById('card-' + gid);
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'scale(0.95)';
        card.style.transition = 'all 0.3s';
        setTimeout(() => card.remove(), 300);
      }
      showToast('Граф удалён');
    } else {
      const d = await r.json();
      showToast(d.error || 'Ошибка удаления', true);
      btn.disabled = false;
      btn.textContent = '🗑';
    }
  } catch (e) {
    showToast('Ошибка сети', true);
    btn.disabled = false;
    btn.textContent = '🗑';
  }
}
</script>
</body>
</html>"""


@app.route("/")
def home():
    idx = _load_index()
    graphs = idx.get("graphs", {})
    sorted_graphs = dict(
        sorted(graphs.items(), key=lambda kv: kv[1].get("created_ts", 0), reverse=True)
    )
    total_nodes = sum(g.get("nodes", 0) for g in sorted_graphs.values())
    total_edges = sum(g.get("edges", 0) for g in sorted_graphs.values())
    return render_template_string(
        HOME_TEMPLATE, graphs=sorted_graphs,
        total_nodes=total_nodes, total_edges=total_edges,
    )


# ── Страница-обёртка для просмотра графа ──────────────────────────────────

VIEW_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — GiftGraph Web</title>
<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 100%; height: 100%; overflow: hidden; background: #050816; }
  body {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
    display: flex; flex-direction: column;
  }
  .toolbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.6rem 1rem; gap: 0.75rem;
    background: rgba(10,14,30,0.88); border-bottom: 1px solid rgba(255,255,255,0.07);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    z-index: 100; flex-shrink: 0; flex-wrap: wrap;
  }
  .toolbar .left { display: flex; align-items: center; gap: 0.6rem; min-width: 0; flex: 1; }
  .toolbar .right { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
  .toolbar .title {
    font-weight: 700; font-size: 0.95rem; color: #e5e7eb;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .toolbar .meta { font-size: 0.7rem; color: #64748b; white-space: nowrap; }
  .tbtn {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.35rem 0.65rem; border-radius: 8px; font-size: 0.78rem;
    font-weight: 600; cursor: pointer; border: 1px solid rgba(255,255,255,0.10);
    background: rgba(255,255,255,0.05); color: #94a3b8;
    transition: all 0.15s; text-decoration: none; white-space: nowrap;
  }
  .tbtn:hover { background: rgba(255,255,255,0.12); color: #e5e7eb; }
  .tbtn.danger { color: #f87171; }
  .tbtn.danger:hover { background: rgba(248,113,113,0.12); color: #fca5a5; }
  .graph-wrap { flex: 1; position: relative; overflow: hidden; }
  .graph-wrap iframe {
    position: absolute; inset: 0; width: 100%; height: 100%;
    border: none; background: #050816;
  }
  @media (max-width: 480px) {
    .toolbar { padding: 0.5rem 0.7rem; }
    .toolbar .meta { display: none; }
  }
</style>
</head>
<body>
<div class="toolbar">
  <div class="left">
    <a href="/" class="tbtn">← Назад</a>
    <div>
      <div class="title">{{ label }}</div>
      <div class="meta">{{ nodes }} узлов · {{ edges }} рёбер{% if path_length %} · путь {{ path_length }} шаг.{% endif %}</div>
    </div>
  </div>
  <div class="right">
    <button class="tbtn danger" onclick="doDelete()" title="Удалить граф">🗑 Удалить</button>
  </div>
</div>
<div class="graph-wrap">
  <iframe src="/graph/{{ gid }}" allowfullscreen></iframe>
</div>

<div id="toast" style="position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);background:rgba(10,14,30,0.92);border:1px solid rgba(255,255,255,0.12);border-radius:12px;padding:0.6rem 1.2rem;color:#e5e7eb;font-size:0.8rem;z-index:999;backdrop-filter:blur(14px);opacity:0;pointer-events:none;transition:opacity 0.25s;box-shadow:0 12px 40px rgba(0,0,0,0.3);"></div>

<script>
function toast(msg, err) {
  var t = document.getElementById('toast');
  t.textContent = msg; t.style.opacity = '1';
  if (err) t.style.borderColor = 'rgba(248,113,113,0.35)';
  else t.style.borderColor = 'rgba(255,255,255,0.12)';
  clearTimeout(t._t); t._t = setTimeout(function(){ t.style.opacity = '0'; }, 2200);
}

async function doDelete() {
  if (!confirm('Удалить этот граф навсегда?')) return;
  try {
    var r = await fetch('/api/graphs/{{ gid }}', { method: 'DELETE' });
    if (r.ok) { toast('Граф удалён. Возвращаемся...'); setTimeout(function(){ location.href = '/'; }, 1000); }
    else { var d = await r.json(); toast(d.error || 'Ошибка', true); }
  } catch(e) { toast('Ошибка сети', true); }
}
</script>
</body>
</html>"""


@app.route("/view/<gid>")
def view_graph_wrapped(gid: str):
    idx = _load_index()
    info = idx.get("graphs", {}).get(gid)
    if info is None:
        abort(404)
    return render_template_string(
        VIEW_TEMPLATE,
        gid=gid,
        title=info.get("label", gid),
        label=info.get("label", gid),
        nodes=info.get("nodes", "?"),
        edges=info.get("edges", "?"),
        path_length=info.get("path_length"),
    )


# ── Raw HTML графа (для iframe) ───────────────────────────────────────────

@app.route("/graph/<gid>")
def view_graph_raw(gid: str):
    graph_file = os.path.join(GRAPHS_DIR, f"{gid}.html")
    if not os.path.exists(graph_file):
        abort(404)
    return send_from_directory(GRAPHS_DIR, f"{gid}.html")


# ── API ───────────────────────────────────────────────────────────────────

@app.route("/api/graphs", methods=["POST"])
def api_create_graph():
    if not _api_key_ok():
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    html = (data.get("html") or "").strip()
    if not html:
        return jsonify({"error": "missing html"}), 400

    gid = uuid.uuid4().hex[:12]
    graph_file = os.path.join(GRAPHS_DIR, f"{gid}.html")
    with open(graph_file, "w", encoding="utf-8") as f:
        f.write(html)

    now = datetime.now(timezone.utc)
    label = data.get("label", f"Граф {gid[:6]}")
    nodes = data.get("nodes", 0)
    edges = data.get("edges", 0)
    path_length = data.get("path_length", 0)

    idx = _load_index()
    idx.setdefault("graphs", {})[gid] = {
        "label": label,
        "nodes": nodes,
        "edges": edges,
        "path_length": path_length,
        "created": now.strftime("%Y-%m-%d %H:%M UTC"),
        "created_ts": now.timestamp(),
    }
    _save_index(idx)

    return jsonify({"id": gid, "url": f"/view/{gid}", "raw_url": f"/graph/{gid}"}), 201


@app.route("/api/graphs/<gid>", methods=["DELETE"])
def api_delete_graph(gid: str):
    if not _api_key_ok():
        return jsonify({"error": "unauthorized"}), 401

    idx = _load_index()
    if gid not in idx.get("graphs", {}):
        return jsonify({"error": "not found"}), 404

    graph_file = os.path.join(GRAPHS_DIR, f"{gid}.html")
    if os.path.exists(graph_file):
        os.unlink(graph_file)

    del idx["graphs"][gid]
    _save_index(idx)

    return jsonify({"deleted": gid})


# ── Статус ────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    graph_count = len([f for f in os.listdir(GRAPHS_DIR) if f.endswith(".html")])
    return jsonify({"status": "ok", "graphs": graph_count})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5100"))
    print(f"🔮 GiftGraph Web starting on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
