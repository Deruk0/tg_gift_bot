"""
Визуализация графа в стиле Obsidian через PyVis.

Новый режим:
- граф статичный после первоначальной стабилизации,
- фон и сетка живут в координатах графа, без параллакс-сдвига canvas,
- HTML занимает весь экран без отступов,
- есть переключатель темы,
- одинаковые связи агрегируются в одну толстую линию.

Пайплайн:
  GraphData → PyVis Network → HTML-файл → отправка пользователю.

PNG-режим оставлен для совместимости, но основной путь — HTML.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import tempfile
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import deque

from pyvis.network import Network

logger = logging.getLogger(__name__)

COLORS = {
    "dark": {
        "page": "#0d0f12",
        "page_glow": "rgba(213, 150, 69, 0.10)",
        "panel": "rgba(20, 22, 25, 0.76)",
        "panel_strong": "rgba(30, 32, 36, 0.94)",
        "border": "rgba(241, 238, 230, 0.15)",
        "text": "#f1eee6",
        "muted": "#ada69a",
        "start_node": "#e8dfcf",
        "path_node": "#c9ad78",
        "regular": "#7aa6a1",
        "anonymous": "#d59645",
        "bot": "#8d929a",
        "edge": "#596068",
        "edge_path": "#b69c6d",
        "edge_start": "#d59645",
        "shadow": "rgba(213, 150, 69, 0.22)",
        "button_bg": "rgba(241, 238, 230, 0.07)",
        "button_hover": "rgba(241, 238, 230, 0.13)",
    },
    "light": {
        "page": "#f2eee6",
        "page_glow": "rgba(169, 103, 31, 0.12)",
        "panel": "rgba(255, 252, 245, 0.78)",
        "panel_strong": "rgba(255, 254, 250, 0.96)",
        "border": "rgba(26, 27, 28, 0.14)",
        "text": "#17191b",
        "muted": "#65615a",
        "start_node": "#17191b",
        "path_node": "#8a6b40",
        "regular": "#527f7a",
        "anonymous": "#a9671f",
        "bot": "#69707a",
        "edge": "#8b908e",
        "edge_path": "#8a6b40",
        "edge_start": "#a9671f",
        "shadow": "rgba(57, 46, 29, 0.18)",
        "button_bg": "rgba(26, 27, 28, 0.05)",
        "button_hover": "rgba(26, 27, 28, 0.09)",
    },
}

BASE_THEME = "dark"

PYVIS_OPTIONS = """
{
  "nodes": {
    "borderWidth": 2,
    "shadow": { "enabled": true, "color": "rgba(213, 150, 69, 0.16)", "size": 8, "x": 0, "y": 0 }
  },
  "edges": {
    "smooth": { "enabled": true, "type": "dynamic", "roundness": 0.18 },
    "arrows": { "to": { "enabled": true, "scaleFactor": 0.45 }, "from": { "enabled": true, "scaleFactor": 0.45 } }
  },
  "layout": {
    "improvedLayout": false,
    "randomSeed": 42
  },
  "physics": {
    "enabled": true,
    "forceAtlas2Based": {
      "gravitationalConstant": -350,
      "centralGravity": 0.005,
      "springLength": 350,
      "springConstant": 0.04,
      "damping": 0.45,
      "avoidOverlap": 1.0
    },
    "solver": "forceAtlas2Based",
    "stabilization": {
      "enabled": true,
      "iterations": 300,
      "updateInterval": 20,
      "fit": true
    }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 100,
    "hideEdgesOnDrag": false,
    "dragNodes": true,
    "dragView": true,
    "zoomView": true,
    "navigationButtons": false,
    "keyboard": false
  }
}
"""


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 11 <= n_abs <= 19:
        return many
    if n1 == 1:
        return one
    if 2 <= n1 <= 4:
        return few
    return many


def _edge_width(count: int, on_path: bool) -> float:
    base = 1.3 + math.log2(count + 1) * 1.25
    if on_path:
        base += 1.1
    return min(base, 10.5)


def _theme_colors(theme: str) -> Dict[str, str]:
    return COLORS[theme if theme in COLORS else BASE_THEME]


def _node_kind(node_id: str, start_node: str, path_nodes: Set[str], anonymous: bool, is_bot: bool) -> str:
    if node_id == start_node:
        return "start"
    if node_id in path_nodes:
        return "path"
    if is_bot:
        return "bot"
    if anonymous:
        return "anonymous"
    return "regular"


def _compute_visual_data(graph_data: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    start_node = str(graph_data.get("start", ""))
    path_nodes: Set[str] = set(graph_data.get("paths", []))

    degrees: Dict[str, int] = defaultdict(int)
    reverse_adj: Dict[str, Set[str]] = defaultdict(set)
    children_map: Dict[str, Set[str]] = defaultdict(set)
    parents_map: Dict[str, Set[str]] = defaultdict(set)
    seen_edges: Set[tuple] = set()
    for src, dst, _label in graph_data.get("edges", []):
        src = str(src)
        dst = str(dst)
        if src == dst:
            continue  # skip self-gifts
        if (src, dst) in seen_edges:
            continue  # deduplicate — degree counts unique connections
        seen_edges.add((src, dst))
        degrees[src] += 1
        degrees[dst] += 1
        reverse_adj[dst].add(src)
        children_map[dst].add(src)
        parents_map[src].add(dst)

    tree_levels: Dict[str, int] = {}
    if start_node:
        queue: deque[str] = deque([start_node])
        tree_levels[start_node] = 0
        while queue:
            node_id = queue.popleft()
            current_level = tree_levels[node_id]
            children = sorted(
                reverse_adj.get(node_id, set()),
                key=lambda nid: (-degrees.get(nid, 0), str(graph_data.get("nodes", {}).get(nid, {}).get("label", nid)).lower(), nid),
            )
            for child in children:
                if child in tree_levels:
                    continue
                tree_levels[child] = current_level + 1
                queue.append(child)

    node_meta: Dict[str, Dict[str, Any]] = {}
    for node_id, node_data in graph_data.get("nodes", {}).items():
        label = str(node_data.get("label", node_id))
        anonymous = bool(node_data.get("anonymous", False))
        is_bot = bool(node_data.get("is_bot", False))
        kind = _node_kind(node_id, start_node, path_nodes, anonymous, is_bot)
        degree = int(degrees.get(node_id, 0))
        level = tree_levels.get(node_id)
        if node_id.startswith("id_") and kind != "start":
            label = node_id
            node_data["label"] = label
            node_data["title"] = f"Отправитель без username: {label}"

        if kind == "start":
            size = 44
        elif kind == "path":
            size = 26 + min(degree, 14) * 1.2
        elif kind == "bot":
            size = 18 + min(degree, 16) * 0.8
        elif kind == "anonymous":
            size = 14 + min(degree, 8) * 0.5
        else:
            size = 20 + min(degree, 18) * 1.0

        node_meta[node_id] = {
            "kind": kind,
            "label": label,
            "anonymous": anonymous,
            "is_bot": is_bot,
            "degree": degree,
            "level": level,
            "size": round(size, 1),
            "leaf": (node_id != start_node and len(children_map.get(node_id, set())) == 0),
            "parents": json.dumps(sorted(children_map.get(node_id, set()))),
            "title": (
                f"Начало поиска: {label} · связей: {degree}"
                if kind == "start"
                else f"На пути: {label} · связей: {degree}"
                if kind == "path"
                else f"Бот · связей: {degree}"
                if kind == "bot"
                else f"Анонимный отправитель · связей: {degree}"
                if kind == "anonymous"
                else f"{node_data.get('title', label)} · связей: {degree}"
            ),
        }

    path_edge_set: Set[Tuple[str, str]] = set()
    path_nodes_list = list(graph_data.get("paths", []))
    for i in range(len(path_nodes_list) - 1):
        a = path_nodes_list[i]
        b = path_nodes_list[i + 1]
        path_edge_set.add((a, b))
        path_edge_set.add((b, a))

    # Группируем: (src, dst) → count подарков
    grouped_edges: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(lambda: {"count": 0})
    for src, dst, _label in graph_data.get("edges", []):
        if src == dst:
            continue
        key = (str(src), str(dst))
        grouped_edges[key]["count"] += 1

    # Детектируем взаимные рёбра (A→B и B→A с подарками)
    mutual_pairs: Set[Tuple[str, str]] = set()
    merged_groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    processed = set()
    for (a, b), info in grouped_edges.items():
        if (a, b) in processed:
            continue
        reverse = (b, a)
        if reverse in grouped_edges and reverse not in processed:
            # Взаимное ребро — объединяем
            total = info["count"] + grouped_edges[reverse]["count"]
            merged_groups[(a, b)] = {"count": total, "mutual": True}
            mutual_pairs.add((a, b))
            mutual_pairs.add((b, a))
            processed.add((a, b))
            processed.add(reverse)
        else:
            merged_groups[(a, b)] = {"count": info["count"], "mutual": False}
            processed.add((a, b))

    edges_meta: List[Dict[str, Any]] = []
    for idx, ((src, dst), info) in enumerate(merged_groups.items()):
        count = int(info["count"])
        mutual = bool(info["mutual"])
        on_path = (src, dst) in path_edge_set or (dst, src) in path_edge_set
        edges_meta.append(
            {
                "id": f"edge_{idx}",
                "from": src,
                "to": dst,
                "count": count,
                "mutual": mutual,
                "on_path": on_path,
                "width": _edge_width(count, on_path),
                "label": "",
                "title": f"{count} {_ru_plural(count, 'подарок', 'подарка', 'подарков')}" + (" · взаимный обмен" if mutual else ""),
            }
        )

    summary = {
        "nodes": len(node_meta),
        "edges": len(edges_meta),
        "path_length": max(0, len(graph_data.get("paths", [])) - 1),
        "has_path": bool(graph_data.get("paths")),
        "start": start_node,
    }

    return node_meta, edges_meta, summary


def _build_pyvis_network(
    graph_data: Dict[str, Any],
    node_meta: Dict[str, Dict[str, Any]],
    edges_meta: List[Dict[str, Any]],
) -> Network:
    theme = _theme_colors(BASE_THEME)

    net = Network(
        height="100vh",
        width="100%",
        bgcolor=theme["page"],
        font_color=theme["text"],
        directed=True,
        cdn_resources="remote",
    )
    net.set_options(PYVIS_OPTIONS)

    for node_id, meta in node_meta.items():
        kind = meta["kind"]
        if kind == "start":
            node_color = {"background": theme["start_node"], "border": theme["text"]}
            font_color = theme["text"]
            bold = True
        elif kind == "path":
            node_color = {"background": theme["path_node"], "border": theme["edge_path"]}
            font_color = theme["text"]
            bold = False
        elif kind == "anonymous":
            node_color = {"background": theme["anonymous"], "border": theme["edge"]}
            font_color = theme["muted"]
            bold = False
        elif kind == "bot":
            node_color = {"background": theme["bot"], "border": theme["edge"]}
            font_color = theme["text"]
            bold = False
        else:
            node_color = {"background": theme["regular"], "border": theme["edge"]}
            font_color = theme["text"]
            bold = False

        net.add_node(
            node_id,
            label=meta["label"] if kind != "anonymous" else "?",
            color=node_color,
            size=meta["size"],
            font={"color": font_color, "size": 14 if kind not in ("anonymous", "bot") else 10, "bold": bold},
            title=meta["title"],
            shape="dot",
        )

    for edge in edges_meta:
        arrows = "to, from" if edge.get("mutual") else "to"
        net.add_edge(
            edge["from"],
            edge["to"],
            id=edge["id"],
            color=theme["edge_path"] if edge["on_path"] else theme["edge"],
            width=edge["width"],
            label="",
            title=edge["title"],
            arrows=arrows,
        )

    return net


def _inject_theme_shell(html: str, meta: Dict[str, Any]) -> str:
    theme_payload = json.dumps(meta, ensure_ascii=False)
    theme_json = json.dumps(COLORS, ensure_ascii=False)

    head_block = """
<script>
  (function(){
    var t = 'dark';
    try { t = localStorage.getItem('giftgraph-theme') || 'dark'; } catch(e){}
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.style.background = t === 'light' ? '#f2eee6' : '#0d0f12';
  })();
</script>
<style>
  html, body {
    width: 100%;
    height: 100%;
    margin: 0;
    overflow: hidden;
    background: var(--giftgraph-page);
    color: var(--giftgraph-text);
  }

  body {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    position: relative;
    transition: background 160ms ease, color 160ms ease;
  }

  /* Empty <center><h1></h1></center> headers emitted by PyVis */
  center {
    display: none !important;
  }

  /* Gradient background sits BEHIND the graph */
  #giftgraph-bg {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    z-index: 0;
    background:
      radial-gradient(circle at 20% 20%, var(--giftgraph-glow), transparent 36%),
      radial-gradient(circle at 80% 80%, rgba(122, 166, 161, 0.10), transparent 30%),
      linear-gradient(180deg, var(--giftgraph-page), var(--giftgraph-page));
  }

  /* PyVis wraps #mynetwork in a bootstrap .card — neutralize it */
  .card {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    z-index: 1;
  }

  /* UI layer floats on top WITHOUT covering / blocking the graph */
  #giftgraph-shell {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    z-index: 40;
    pointer-events: none;
  }

  #mynetwork {
    position: absolute !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    float: none !important;
    overflow: hidden !important;
    touch-action: none;
  }

  #giftgraph-ui {
    position: absolute;
    top: 18px;
    left: 18px;
    right: 18px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    z-index: 40;
    pointer-events: none;
  }

  #giftgraph-card, #giftgraph-actions {
    pointer-events: auto;
  }

  #giftgraph-card {
    max-width: min(760px, calc(100vw - 260px));
    padding: 14px 16px;
    font-size: 12px;
    border-radius: 20px;
    background: var(--giftgraph-panel);
    border: 1px solid var(--giftgraph-border);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.26);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
  }

  #giftgraph-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
  }

  #giftgraph-subtitle {
    color: var(--giftgraph-muted);
    font-size: 13px;
    line-height: 1.5;
  }

  #giftgraph-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  .giftgraph-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 999px;
    border: 1px solid var(--giftgraph-border);
    background: rgba(255, 255, 255, 0.04);
    color: var(--giftgraph-text);
    font-size: 12px;
    line-height: 1;
    white-space: nowrap;
  }

  .giftgraph-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.03);
    flex: 0 0 auto;
  }

  #giftgraph-actions {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }

  .giftgraph-button {
    border: 1px solid var(--giftgraph-border);
    background: var(--giftgraph-button);
    color: var(--giftgraph-text);
    border-radius: 16px;
    padding: 12px 14px;
    font-size: 13px;
    font-weight: 700;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
    cursor: pointer;
    transition: transform 140ms ease, background 140ms ease, border-color 140ms ease;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
  }

  .giftgraph-button:hover {
    transform: translateY(-1px);
    background: var(--giftgraph-button-hover);
  }

  .giftgraph-button:active {
    transform: translateY(0px) scale(0.99);
  }

  .giftgraph-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-width: 42px;
    padding: 12px 14px;
    border-radius: 16px;
    border: 1px solid var(--giftgraph-border);
    background: var(--giftgraph-panel);
    color: var(--giftgraph-text);
    font-size: 13px;
    font-weight: 700;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  }

  #giftgraph-hint {
    position: absolute;
    left: 18px;
    bottom: 18px;
    z-index: 40;
    pointer-events: none;
    color: var(--giftgraph-muted);
    font-size: 12px;
    background: var(--giftgraph-panel);
    border: 1px solid var(--giftgraph-border);
    padding: 10px 12px;
    border-radius: 14px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.16);
  }

  .vis-network canvas {
    transition: filter 160ms ease;
  }

  .vis-tooltip {
    font-family: inherit !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    background: rgba(15, 23, 42, 0.94) !important;
    color: #f8fafc !important;
    box-shadow: 0 16px 60px rgba(0, 0, 0, 0.32) !important;
    padding: 10px 12px !important;
  }

  html {
    background: #050816;
  }

  [data-theme="dark"] {
    --giftgraph-page: #0d0f12;
    --giftgraph-panel: rgba(20, 22, 25, 0.82);
    --giftgraph-border: rgba(241, 238, 230, 0.15);
    --giftgraph-text: #f1eee6;
    --giftgraph-muted: #ada69a;
    --giftgraph-glow: rgba(213, 150, 69, 0.10);
    --giftgraph-accent: #d59645;
    --giftgraph-accent-2: #7aa6a1;
    --giftgraph-button: rgba(241, 238, 230, 0.07);
    --giftgraph-button-hover: rgba(241, 238, 230, 0.13);
  }

  [data-theme="light"] {
    --giftgraph-page: #f2eee6;
    --giftgraph-panel: rgba(255, 252, 245, 0.84);
    --giftgraph-border: rgba(26, 27, 28, 0.14);
    --giftgraph-text: #17191b;
    --giftgraph-muted: #65615a;
    --giftgraph-glow: rgba(169, 103, 31, 0.12);
    --giftgraph-accent: #a9671f;
    --giftgraph-accent-2: #527f7a;
    --giftgraph-button: rgba(26, 27, 28, 0.05);
    --giftgraph-button-hover: rgba(26, 27, 28, 0.09);
  }
</style>
"""

    body_block = """
<div id="giftgraph-bg"></div>
<div id="giftgraph-shell" data-theme="dark" data-meta='__THEME_PAYLOAD__' data-palette='__THEME_JSON__'>
  <div id="giftgraph-ui">
    <div id="giftgraph-card">
      <div id="giftgraph-title">⟢ GiftGraph</div>
      <div id="giftgraph-subtitle">
        Узлов: <b>{nodes}</b> · Рёбер: <b>{edges}</b>
      </div>
      <div id="giftgraph-legend">
        <span class="giftgraph-pill"><span class="giftgraph-dot" data-kind="start" style="background:{start_color}"></span>Старт</span>
        <span class="giftgraph-pill"><span class="giftgraph-dot" data-kind="regular" style="background:{regular_color}"></span>Обычный узел</span>
        <span class="giftgraph-pill"><span class="giftgraph-dot" data-kind="anonymous" style="background:{anonymous_color}"></span>Анонимный</span>
        <span class="giftgraph-pill"><span class="giftgraph-dot" data-kind="bot" style="background:{bot_color}"></span>Бот</span>
      </div>
    </div>
    <div id="giftgraph-actions">
      <button id="giftgraph-theme-toggle" class="giftgraph-button" type="button">Темная</button>
    </div>
  </div>
  <div id="giftgraph-hint">Колесо: масштаб · drag: панорама и узлы</div>
</div>
""".format(
        nodes=meta["summary"]["nodes"],
        edges=meta["summary"]["edges"],
        start_color=COLORS['dark']['start_node'],
        regular_color=COLORS['dark']['regular'],
        anonymous_color=COLORS['dark']['anonymous'],
        bot_color=COLORS['dark']['bot'],
    )

    script_block = """
<script>
(function() {
  const META      = JSON.parse(document.getElementById('giftgraph-shell').dataset.meta);
  const PALETTE   = JSON.parse(document.getElementById('giftgraph-shell').dataset.palette);
  const shell     = document.getElementById('giftgraph-shell');
  const bg        = document.getElementById('giftgraph-bg');
  const container = document.getElementById('mynetwork');
  const toggle    = document.getElementById('giftgraph-theme-toggle');
  const subtitle  = document.getElementById('giftgraph-subtitle');
  const legendDots = Array.from(document.querySelectorAll('.giftgraph-dot'));

  // ── per-hover saved state (keyed by node id) ──────────────────────────
  let _hoverSaved = {};

  // ── theme helpers ─────────────────────────────────────────────────────
  function currentTheme() {
    try { return localStorage.getItem('giftgraph-theme') || 'dark'; }
    catch(e) { return 'dark'; }
  }
  function saveTheme(t) {
    try { localStorage.setItem('giftgraph-theme', t); } catch(e) {}
  }

  // ── network accessor ──────────────────────────────────────────────────
  function getNetwork() {
    try { return typeof network !== 'undefined' ? network : (window.network || null); }
    catch(e) { return window.network || null; }
  }

  // ── node/edge style from palette ──────────────────────────────────────
  function nodeBaseSize(info) {
    const degree = info.degree || 0;
    if (info.kind === 'start')     return 44;
    if (info.kind === 'path')      return 26 + Math.min(degree, 14) * 1.2;
    if (info.kind === 'bot')       return 18 + Math.min(degree, 16) * 0.8;
    if (info.kind === 'anonymous') return 14 + Math.min(degree, 8)  * 0.5;
    return 20 + Math.min(degree, 18) * 1.0;
  }

  function nodeStyle(info, palette) {
    const size = nodeBaseSize(info);
    const fontBase = info.kind === 'start' ? 17 : info.kind === 'anonymous' || info.kind === 'bot' ? 9 : 13;
    if (info.kind === 'start')
      return { color: { background: palette.start_node, border: palette.text },
               size, font: { color: palette.text,  size: fontBase, bold: true  } };
    if (info.kind === 'path')
      return { color: { background: palette.path_node,  border: palette.edge_path },
               size, font: { color: palette.text,  size: fontBase, bold: false } };
    if (info.kind === 'anonymous')
      return { color: { background: palette.anonymous,  border: palette.edge },
               size, font: { color: palette.muted, size: fontBase, bold: false } };
    if (info.kind === 'bot')
      return { color: { background: palette.bot,  border: palette.edge },
               size, font: { color: palette.text, size: fontBase, bold: false } };
    return   { color: { background: palette.regular,    border: palette.edge },
               size, font: { color: palette.text,  size: fontBase, bold: false } };
  }

  function edgeStyle(edge, palette) {
    const color = edge.on_path ? palette.edge_path : palette.edge;
    const arrows = edge.mutual
      ? { to: { enabled: true, scaleFactor: 0.45 }, from: { enabled: true, scaleFactor: 0.45 } }
      : { to: { enabled: true, scaleFactor: 0.45 }, from: { enabled: false } };
    return { color, width: edge.width, arrows };
  }

  // build a fast id→meta lookup for edges
  const _edgeMeta = {};
  META.edges.forEach(e => { _edgeMeta[e.id] = e; });

  // ── theme ─────────────────────────────────────────────────────────────
  function applyTheme(themeName) {
    // restore any hovered node first, then clear state
    _restoreAllHovered();
    _hoverSaved = {};

    const palette = PALETTE[themeName] || PALETTE.dark;
    const net = getNetwork();

    document.documentElement.setAttribute('data-theme', themeName);
    if (shell) shell.setAttribute('data-theme', themeName);

    const grad = `radial-gradient(circle at 20% 20%, ${palette.page_glow}, transparent 36%),`
               + `radial-gradient(circle at 80% 80%, rgba(122,166,161,0.10), transparent 30%),`
               + `linear-gradient(180deg, ${palette.page}, ${palette.page})`;
    [document.body, bg].forEach(el => {
      if (!el) return;
      el.style.background = palette.page;
      el.style.backgroundImage = grad;
    });
    if (container) container.style.background = 'transparent';
    if (toggle)   toggle.textContent = themeName === 'light' ? 'Темная' : 'Светлая';
    if (subtitle) subtitle.style.color = palette.muted;
    legendDots.forEach(dot => {
      const k = dot.getAttribute('data-kind');
      if (k === 'start')     dot.style.background = palette.start_node;
      if (k === 'regular')   dot.style.background = palette.regular;
      if (k === 'anonymous') dot.style.background = palette.anonymous;
      if (k === 'bot')      dot.style.background = palette.bot;
    });

    try {
      if (net && net.body && net.body.data) {
        try {
          const nodeUpdates = Object.entries(META.nodes).map(([id, info]) => {
            const st = nodeStyle(info, palette);
            return { id, color: st.color, size: st.size, font: st.font, title: info.title };
          });
          const edgeUpdates = META.edges.map(edge => {
            const st = edgeStyle(edge, palette);
            return { id: edge.id, color: st.color, width: st.width, arrows: st.arrows };
          });
          net.body.data.nodes.update(nodeUpdates);
          net.body.data.edges.update(edgeUpdates);
          // Re-apply slider scales to preserve user settings across theme switch
          (function(){
            const sliders = document.getElementById('sns');
            if (sliders) {
              const ns = parseFloat(sliders.value) || 1;
              const es = parseFloat((document.getElementById('ses') || {}).value) || 1;
              _applyScales(net, ns, es);
            }
          })();
        } catch(err) {
          console.warn('GiftGraph applyTheme error:', err);
        }
      }
    } catch(e) {}
  }

  function bindToggle() {
    if (!toggle) return;
    toggle.addEventListener('click', () => {
      const next = currentTheme() === 'light' ? 'dark' : 'light';
      saveTheme(next);
      applyTheme(next);
    });
  }

  // ── settings panel ────────────────────────────────────────────────────
  function buildSettingsPanel() {
    if (!shell || document.getElementById('giftgraph-settings-panel')) return;
    const panel = document.createElement('div');
    panel.id = 'giftgraph-settings-panel';
    panel.style.cssText = 'position:absolute;right:18px;bottom:18px;z-index:40;pointer-events:auto;display:flex;flex-direction:column;gap:8px;align-items:flex-end;';
    panel.innerHTML = `
      <div id="gg-sbox" style="background:var(--giftgraph-panel);border:1px solid var(--giftgraph-border);border-radius:14px;padding:14px;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);width:230px;display:none;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
        <div style="font-size:13px;font-weight:700;color:var(--giftgraph-text);margin-bottom:12px;">Настройки</div>
        <div style="display:flex;flex-direction:column;gap:12px;">
          <label style="font-size:11px;color:var(--giftgraph-muted);display:block;">
            Размер узлов <span id="vns" style="float:right;font-weight:600;color:var(--giftgraph-text);">1.0×</span>
            <input id="sns" type="range" min="0.5" max="2.5" step="0.05" value="1" style="width:100%;margin-top:4px;accent-color:var(--giftgraph-accent);cursor:pointer;">
          </label>
          <label style="font-size:11px;color:var(--giftgraph-muted);display:block;">
            Толщина линий <span id="ves" style="float:right;font-weight:600;color:var(--giftgraph-text);">1.0×</span>
            <input id="ses" type="range" min="0.5" max="3.0" step="0.05" value="1" style="width:100%;margin-top:4px;accent-color:var(--giftgraph-accent);cursor:pointer;">
          </label>
          <label style="font-size:11px;color:var(--giftgraph-muted);display:block;">
            Расстояние <span id="vsp" style="float:right;font-weight:600;color:var(--giftgraph-text);">350</span>
            <input id="ssp" type="range" min="80" max="700" step="10" value="350" style="width:100%;margin-top:4px;accent-color:var(--giftgraph-accent);cursor:pointer;">
          </label>
          <label style="font-size:11px;color:var(--giftgraph-muted);display:block;">
            Расталкивание <span id="vrp" style="float:right;font-weight:600;color:var(--giftgraph-text);">350</span>
            <input id="srp" type="range" min="50" max="800" step="10" value="350" style="width:100%;margin-top:4px;accent-color:var(--giftgraph-accent);cursor:pointer;">
          </label>
          <button id="btn-apply" class="giftgraph-button" type="button" style="width:100%;margin-top:2px;">Применить</button>
          <button id="btn-reshuffle" class="giftgraph-button" type="button" style="width:100%;">Перемешать</button>
        </div>
      </div>
      <button id="btn-settings-toggle" class="giftgraph-button" type="button" title="Настройки">Настройки</button>
    `;
    shell.appendChild(panel);

    // slider live display
    const sliders = [
      { s: 'sns', v: 'vns', fmt: x => x + '×' },
      { s: 'ses', v: 'ves', fmt: x => x + '×' },
      { s: 'ssp', v: 'vsp', fmt: x => x       },
      { s: 'srp', v: 'vrp', fmt: x => x       },
    ];
    sliders.forEach(({ s, v, fmt }) => {
      const el = document.getElementById(s);
      const vl = document.getElementById(v);
      if (!el || !vl) return;
      el.addEventListener('input', () => { vl.textContent = fmt(el.value); });
    });

    document.getElementById('btn-settings-toggle').addEventListener('click', () => {
      const box = document.getElementById('gg-sbox');
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
    });
    document.getElementById('btn-apply').addEventListener('click', applySettings);
    document.getElementById('btn-reshuffle').addEventListener('click', reshuffleGraph);
  }

  function _getSliders() {
    return {
      nodeScale: parseFloat(document.getElementById('sns').value) || 1,
      edgeScale: parseFloat(document.getElementById('ses').value) || 1,
      springLen: parseInt(document.getElementById('ssp').value)   || 350,
      repulsion: -(parseInt(document.getElementById('srp').value) || 350),
    };
  }

  function _applyScales(net, nodeScale, edgeScale) {
    // nodes: iterate via DataSet.get() by ids from META
    const nodeIds = Object.keys(META.nodes);
    const nodeUpdates = nodeIds.map(id => {
      const info = META.nodes[id];
      const base = nodeBaseSize(info);
      const baseFont = info.kind === 'start' ? 17 : info.kind === 'anonymous' ? 9 : 13;
      return { id, size: base * nodeScale, font: { size: Math.round(baseFont * nodeScale) } };
    });
    net.body.data.nodes.update(nodeUpdates);

    // edges: use id-based lookup
    const edgeUpdates = META.edges.map(e => ({ id: e.id, width: e.width * edgeScale }));
    net.body.data.edges.update(edgeUpdates);
  }

  function applySettings() {
    const net = getNetwork();
    if (!net || !net.body || !net.body.data) return;
    _restoreAllHovered();
    _hoverSaved = {};
    const { nodeScale, edgeScale, springLen, repulsion } = _getSliders();
    net.setOptions({
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: repulsion,
          centralGravity: 0.005,
          springLength: springLen,
          springConstant: 0.04,
          damping: 0.45,
          avoidOverlap: 1.0,
        },
        stabilization: { enabled: true, iterations: 250, fit: true },
      },
    });
    _applyScales(net, nodeScale, edgeScale);
  }

  function reshuffleGraph() {
    const net = getNetwork();
    if (!net) return;
    _restoreAllHovered();
    _hoverSaved = {};
    const { nodeScale, edgeScale, springLen, repulsion } = _getSliders();
    // randomise positions slightly
    const pos = net.getPositions();
    const updates = Object.keys(pos).map(id => ({
      id,
      x: pos[id].x + (Math.random() - 0.5) * 400,
      y: pos[id].y + (Math.random() - 0.5) * 400,
    }));
    net.body.data.nodes.update(updates);
    net.setOptions({
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: repulsion,
          centralGravity: 0.005,
          springLength: springLen,
          springConstant: 0.04,
          damping: 0.45,
          avoidOverlap: 1.0,
        },
        stabilization: { enabled: true, iterations: 250, fit: true },
      },
    });
    _applyScales(net, nodeScale, edgeScale);
  }

  // ── hover ─────────────────────────────────────────────────────────────
  function _restoreAllHovered() {
    const net = getNetwork();
    if (!net || !net.body || !net.body.data) return;
    Object.keys(_hoverSaved).forEach(id => _restoreNode(net, id));
  }

  function _restoreNode(net, id) {
    const s = _hoverSaved[id];
    if (!s) return;
    net.body.data.nodes.update({
      id,
      size:        s.size,
      font:        s.font,
      color:       s.color,
      borderWidth: s.borderWidth,
      shadow:      s.shadow,
    });
    delete _hoverSaved[id];
  }

  function initHover() {
    const net = getNetwork();
    if (!net || !net.on) return;

    net.on('hoverNode', p => {
      if (_hoverSaved[p.node]) return;   // already saved
      const d = net.body.data.nodes.get(p.node);
      if (!d) return;

      const bg = (d.color && typeof d.color === 'object') ? d.color.background : '#7aa6a1';
      // deep-copy current state
      _hoverSaved[p.node] = {
        size:        d.size,
        font:        d.font ? { ...d.font } : { size: 13 },
        color:       d.color ? (typeof d.color === 'object'
                       ? { background: d.color.background, border: d.color.border }
                       : d.color) : {},
        borderWidth: d.borderWidth != null ? d.borderWidth : 2,
        shadow:      d.shadow ? { ...d.shadow } : { enabled: false, color: 'rgba(0,0,0,0)', size: 8, x: 0, y: 0 },
      };

      const newSize = d.size * 2.0;
      const glowColor = bg + 'cc';  // 80% opacity
      net.body.data.nodes.update({
        id:          p.node,
        size:        newSize,
        font:        { size: Math.round((d.font && d.font.size || 13) * 1.6), color: d.font && d.font.color, bold: d.font && d.font.bold },
        borderWidth: 5,
        shadow:      { enabled: true, color: glowColor, size: 40, x: 0, y: 0 },
      });
    });

    net.on('blurNode', p => {
      setTimeout(() => _restoreNode(net, p.node), 60);
    });
  }

  // ── bot leaf toggle ──────────────────────────────────────────────────
  let _botToggled = {};   // bot node id → true (leaves hidden)

  function toggleBotLeaves(botId) {
    const net = getNetwork();
    if (!net || !net.body || !net.body.data) return;
    const nodeInfo = META.nodes[botId];
    if (!nodeInfo || nodeInfo.kind !== 'bot') return;

    const isHidden = _botToggled[botId];
    const edgeUpdates = [];

    META.edges.forEach(edge => {
      const otherId = edge.from === botId ? edge.to : (edge.to === botId ? edge.from : null);
      if (!otherId) return;
      const otherNode = META.nodes[otherId];
      if (!otherNode || !otherNode.leaf) return;
      edgeUpdates.push({ id: edge.id, hidden: !isHidden });
    });

    if (edgeUpdates.length > 0) {
      net.body.data.edges.update(edgeUpdates);
      _botToggled[botId] = !isHidden;
      const palette = PALETTE[currentTheme()] || PALETTE.dark;
      net.body.data.nodes.update({
        id: botId,
        borderWidth: isHidden ? 2 : 3,
        color: {
          background: palette.bot,
          border: isHidden ? '#0d9488' : '#f59e0b'
        },
        title: isHidden
          ? (nodeInfo.title || 'Бот')
          : ((nodeInfo.title || 'Бот') + ' · листья скрыты')
      });
    }
  }

  function initBotClicks() {
    const net = getNetwork();
    if (!net || !net.on) return;
    net.on('click', p => {
      if (p.nodes.length === 1) {
        const nodeId = p.nodes[0];
        const info = META.nodes[nodeId];
        if (info && info.kind === 'bot') {
          toggleBotLeaves(nodeId);
        }
      }
    });
  }

  // ── leaf pull ─────────────────────────────────────────────────────────
  function postProcessLayout() {
    const net = getNetwork();
    if (!net || !net.body || !net.body.data) return;
    const positions = net.getPositions();
    const updates = [];

    Object.entries(META.nodes).forEach(([id, info]) => {
      if (!info.leaf) return;
      let parentIds = [];
      try { parentIds = JSON.parse(info.parents || '[]'); } catch(e) {}
      if (!parentIds.length) return;

      let sx = 0, sy = 0, cnt = 0;
      parentIds.forEach(pid => {
        const p = positions[pid];
        if (p) { sx += p.x; sy += p.y; cnt++; }
      });
      if (!cnt) return;

      const cx = sx / cnt, cy = sy / cnt;
      const cur = positions[id];
      if (!cur) return;
      const pull = 0.75;
      updates.push({ id, x: cur.x + (cx - cur.x) * pull, y: cur.y + (cy - cur.y) * pull });
    });

    if (updates.length) {
      net.body.data.nodes.update(updates);
      net.fit();
    }
  }

  // ── bootstrap ─────────────────────────────────────────────────────────
  buildSettingsPanel();
  bindToggle();

  // Apply theme immediately so CSS vars are correct before network loads
  (function initTheme() {
    const t = currentTheme();
    document.documentElement.setAttribute('data-theme', t);
    if (shell) shell.setAttribute('data-theme', t);
    const palette = PALETTE[t] || PALETTE.dark;
    const grad = `radial-gradient(circle at 20% 20%, ${palette.page_glow}, transparent 36%),`
               + `radial-gradient(circle at 80% 80%, rgba(122,166,161,0.10), transparent 30%),`
               + `linear-gradient(180deg, ${palette.page}, ${palette.page})`;
    [document.body, bg].forEach(el => {
      if (!el) return;
      el.style.background = palette.page;
      el.style.backgroundImage = grad;
    });
    if (toggle) toggle.textContent = t === 'light' ? 'Темная' : 'Светлая';
    if (subtitle) subtitle.style.color = palette.muted;
    legendDots.forEach(dot => {
      const k = dot.getAttribute('data-kind');
      if (k === 'start')     dot.style.background = palette.start_node;
      if (k === 'regular')   dot.style.background = palette.regular;
      if (k === 'anonymous') dot.style.background = palette.anonymous;
      if (k === 'bot')      dot.style.background = palette.bot;
    });
  })();

  // Wait for vis.js to expose `network`, then wire events and apply theme to nodes
  let _bootAttempts = 0;
  function boot() {
    const net = getNetwork();
    if (!net || !net.on) {
      if (++_bootAttempts < 60) setTimeout(boot, 100);
      return;
    }
    initHover();
    initBotClicks();
    // Apply theme to nodes/edges now that network exists
    applyTheme(currentTheme());
    // Re-apply after layout stabilises (positions may shift node sizes)
    const onStable = () => {
      postProcessLayout();
      applyTheme(currentTheme());
    };
    net.once('stabilizationIterationsDone', onStable);
    net.once('stabilized', onStable);
  }
  boot();
})();
</script>
"""

    html = html.replace("</head>", head_block + "</head>")
    html = html.replace("</body>", body_block + script_block + "</body>")
    html = html.replace("__THEME_PAYLOAD__", theme_payload)
    html = html.replace("__THEME_JSON__", theme_json)
    return html


async def render_graph_to_html(graph_data: Dict[str, Any]) -> Optional[str]:
    """
    Строит интерактивный PyVis граф и возвращает HTML-файл.
    HTML можно открыть в браузере: он занимает весь экран, статичен после
    стабилизации и не двигает canvas отдельно от координат графа.
    """
    if not graph_data.get("nodes"):
        logger.warning("render_graph_to_html: получен пустой граф")
        return None

    node_meta, edges_meta, summary = _compute_visual_data(graph_data)
    net = _build_pyvis_network(graph_data, node_meta, edges_meta)

    tmp_html = tempfile.NamedTemporaryFile(suffix="_graph.html", delete=False, mode="w", encoding="utf-8")
    html_path = tmp_html.name
    tmp_html.close()

    try:
        net.write_html(html_path)
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        html = _inject_theme_shell(
            html,
            {
                "start": graph_data.get("start", ""),
                "paths": graph_data.get("paths", []),
                "nodes": node_meta,
                "edges": edges_meta,
                "summary": summary,
            },
        )

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(
            "HTML граф сохранён: %s (узлов: %d, рёбер: %d)",
            html_path,
            summary["nodes"],
            summary["edges"],
        )
        return html_path

    except Exception as exc:
        logger.error("Ошибка при создании HTML графа: %s", exc, exc_info=True)
        try:
            if os.path.exists(html_path):
                os.unlink(html_path)
        except Exception:
            pass
        return None


def cleanup_html(html_path: Optional[str]) -> None:
    """Удалить временный HTML после отправки пользователю."""
    if html_path and os.path.exists(html_path):
        try:
            os.unlink(html_path)
            logger.debug("Временный HTML удалён: %s", html_path)
        except Exception as exc:
            logger.warning("Не удалось удалить временный HTML %s: %s", html_path, exc)


async def render_graph_to_png(graph_data: Dict[str, Any]) -> Optional[str]:
    """
    Совместимость с прежним API: строит HTML и, если доступен Selenium,
    делает PNG-скриншот. Основной путь — HTML.
    """
    html_path = await render_graph_to_html(graph_data)
    if not html_path:
        return None

    png_path = html_path.replace(".html", ".png")
    try:
        success = await asyncio.to_thread(_selenium_render_to_png, html_path, png_path)
        if success and os.path.exists(png_path):
            return png_path
        return None
    finally:
        try:
            if os.path.exists(html_path):
                os.unlink(html_path)
        except Exception:
            pass


def _selenium_render_to_png(html_path: str, png_path: str) -> bool:
    """Рендер HTML в PNG через headless Chrome. Используется только для совместимости."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import time

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1600,1100")
        options.add_argument("--disable-extensions")
        options.add_argument("--log-level=3")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.get(f"file://{html_path}")
            time.sleep(4)
            driver.set_window_size(1600, 1100)
            time.sleep(0.5)
            driver.save_screenshot(png_path)
            logger.info("Скриншот сохранён: %s", png_path)
            return True
        finally:
            driver.quit()
    except Exception as exc:
        logger.error("Ошибка Selenium при рендере графа: %s", exc)
        return False


def cleanup_png(png_path: Optional[str]) -> None:
    """Удалить временный PNG после отправки пользователю."""
    if png_path and os.path.exists(png_path):
        try:
            os.unlink(png_path)
            logger.debug("Временный файл удалён: %s", png_path)
        except Exception as exc:
            logger.warning("Не удалось удалить временный файл %s: %s", png_path, exc)
