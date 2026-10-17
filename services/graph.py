"""
Построение графа социальных связей на основе подарков Telegram.

Два режима:
  tree  — полный BFS-граф от одного пользователя
  path  — поиск кратчайшего пути между несколькими пользователями

Данные хранятся только в памяти (dict/set) в рамках одной сессии.
После отправки результата вызывающий код обязан удалить объект (del).
"""
import asyncio
import logging
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from telethon import TelegramClient

from config import MAX_NODES_PER_GRAPH
from services.parser import REQUEST_DELAY, get_user_gifts

logger = logging.getLogger(__name__)

# Тип данных узла
NodeData = Dict[str, Any]

# Тип данных полного графа
GraphData = Dict[str, Any]
PATH_LEAVES_PER_NODE = 8


# ── Вспомогательные функции ────────────────────────────────────────────────────

def _make_graph() -> GraphData:
    """Инициализировать пустую структуру графа"""
    return {
        "nodes": {},    # node_id -> NodeData
        "edges": [],    # список (src, dst, label)
        "start": "",    # стартовый узел (белый/увеличенный)
        "targets": [],  # целевые узлы для режима path
        "paths": [],    # кратчайший путь [node_id, ...]
    }


def _add_node(graph: GraphData, node_id: str, label: str, anonymous: bool = False, is_bot: bool = False) -> None:
    """Добавить узел в граф (идемпотентно)"""
    if node_id not in graph["nodes"]:
        graph["nodes"][node_id] = {
            "id": node_id,
            "label": label,
            "anonymous": anonymous,
            "is_bot": is_bot,
        }


def _add_edge(graph: GraphData, src: str, dst: str, label: str = "подарок") -> None:
    """Добавить ребро в граф (дубликаты допускаются — PyVis их обработает)"""
    graph["edges"].append((src, dst, label))


def _at(username: str) -> str:
    """Добавить @ к имени пользователя если его нет"""
    return f"@{username}" if not username.startswith("@") else username


# ── Режим tree: BFS-обход от одного пользователя ──────────────────────────────

async def build_tree_graph(
    client: TelegramClient,
    start_username: str,
    depth: int = 2,
    gifts_mode: str = "public",
    no_bots: bool = False,
    *,
    _gift_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> GraphData:
    """
    BFS-обход профилей начиная со start_username.

    На каждом уровне: берём пользователя → запрашиваем его подарки →
    получаем отправителей → добавляем как узлы следующего уровня.

    Args:
        client:         Активный Telethon клиент
        start_username: @username стартового узла
        depth:          Глубина обхода (1-10)
        gifts_mode:     "public" — только явные отправители
                        "all"    — включая анонимные подарки

    Returns:
        GraphData — граф в памяти (удалить после отправки!)
    """
    include_anon = gifts_mode == "all"
    clean_start = start_username.lstrip("@").strip().lower()

    graph = _make_graph()
    graph["start"] = clean_start

    # Добавляем стартовый узел
    _add_node(graph, clean_start, _at(clean_start))

    visited: Set[str] = set()

    # Очередь: (username, текущая_глубина)
    queue: deque[Tuple[str, int]] = deque([(clean_start, 0)])

    while queue:
        current_user, current_depth = queue.popleft()

        # Защита от повторных обходов
        if current_user in visited:
            continue
        visited.add(current_user)

        # Достигли максимальной глубины — узел добавлен, дальше не идём
        if current_depth >= depth:
            continue

        # Защита от переполнения графа
        if len(graph["nodes"]) >= MAX_NODES_PER_GRAPH:
            logger.info(
                "Достигнут лимит узлов (%d), BFS остановлен", MAX_NODES_PER_GRAPH
            )
            break

        logger.debug("BFS: обрабатываем @%s (глубина %d)", current_user, current_depth)

        # Получаем подарки текущего пользователя
        if _gift_cache is not None and current_user in _gift_cache:
            gifts = _gift_cache[current_user]
        else:
            gifts = await get_user_gifts(client, current_user, include_anonymous=include_anon)
            if _gift_cache is not None:
                _gift_cache[current_user] = gifts

        anonymous_count = sum(1 for gift in gifts if gift["anonymous"])
        for gift in gifts:
            if len(graph["nodes"]) >= MAX_NODES_PER_GRAPH:
                break

            if gift["anonymous"]:
                if not include_anon:
                    continue
                # One anonymous group per recipient; never imply a shared sender.
                anon_id = f"anon_{current_user}:gifts"
                if anon_id in graph["nodes"]:
                    continue
                label = f"? ×{anonymous_count}" if anonymous_count > 1 else "?"
                _add_node(graph, anon_id, label, anonymous=True)
                graph["nodes"][anon_id]["gift_count"] = anonymous_count
                # Preserve gift counts used by edge widths, tooltips and statistics.
                for _ in range(anonymous_count):
                    _add_edge(graph, anon_id, current_user)
            else:
                sender = gift["sender_username"]
                if not sender:
                    sender = f"id_{gift['sender_id']}" if gift.get('sender_id') is not None else None
                if not sender:
                    continue

                sender = sender.lstrip("@").strip().lower()
                if no_bots and gift.get("is_bot"):
                    continue
                display_name = _at(sender) if not sender.startswith('id_') else sender
                _add_node(graph, sender, display_name, is_bot=gift.get("is_bot", False))
                _add_edge(graph, sender, current_user)

                # Добавляем отправителя в очередь если не посещён
                if sender not in visited:
                    queue.append((sender, current_depth + 1))

        # Пауза между пользователями для соблюдения rate limit
        await asyncio.sleep(REQUEST_DELAY)

    logger.info(
        "Граф (tree) построен: %d узлов, %d рёбер | старт: @%s, глубина: %d",
        len(graph["nodes"]),
        len(graph["edges"]),
        clean_start,
        depth,
    )
    return graph


# ── Режим path: поиск пути между несколькими пользователями ───────────────────

async def build_path_graph(
    client: TelegramClient,
    usernames: List[str],
    depth: int = 2,
    gifts_mode: str = "public",
    no_bots: bool = False,
) -> GraphData:
    """
    Ищет кратчайший путь между двумя пользователями в объединённом BFS.
    Возвращает только цепочку и ограниченное число листьев в один шаг от неё.

    Args:
        client:    Активный Telethon клиент
        usernames: Ровно два разных пользователя
        depth:     Глубина BFS от каждого узла
        gifts_mode: "public" или "all"

    Returns:
        GraphData с заполненным полем "paths"
    """
    clean_users = list(dict.fromkeys(u.lstrip("@").strip().lower() for u in usernames))
    if len(clean_users) != 2:
        raise ValueError("Для режима path укажите ровно двух разных пользователей")

    # Объединённый граф
    combined = _make_graph()
    combined["start"] = clean_users[0]
    combined["targets"] = clean_users[1:]
    # Reserve room for every requested profile before merging their trees.
    for user in clean_users:
        _add_node(combined, user, _at(user))

    # Список смежности для поиска пути (двунаправленный)
    adjacency: Dict[str, Set[str]] = {}
    gift_cache: Dict[str, List[Dict[str, Any]]] = {}
    edge_counts: Counter = Counter()

    for start_user in clean_users:
        partial = await build_tree_graph(client, start_user, depth, gifts_mode, no_bots=no_bots, _gift_cache=gift_cache)

        # Объединяем узлы
        for node_id, node_data in partial["nodes"].items():
            if node_id not in combined["nodes"] and len(combined["nodes"]) < MAX_NODES_PER_GRAPH:
                combined["nodes"][node_id] = node_data

        # Объединяем рёбра и строим список смежности
        for src, dst, label in partial["edges"]:
            if src not in combined["nodes"] or dst not in combined["nodes"]:
                continue
            # Граф рассматриваем как ненаправленный для поиска пути
            adjacency.setdefault(src, set()).add(dst)
            adjacency.setdefault(dst, set()).add(src)
        # The same recipient can be explored from both roots. Preserve repeated
        # gifts, but do not count the same cached batch twice.
        edge_counts |= Counter(edge for edge in partial["edges"]
                               if edge[0] in combined["nodes"] and edge[1] in combined["nodes"])

    combined["edges"] = list(edge_counts.elements())

    # Ищем кратчайший путь между первыми двумя пользователями
    if len(clean_users) >= 2:
        path = _bfs_shortest_path(adjacency, clean_users[0], clean_users[1])
        combined["paths"] = path

        if path:
            logger.info(
                "Путь найден (%d шагов): %s",
                len(path) - 1,
                " → ".join(_at(p) if not p.startswith("anon_") else "?" for p in path),
            )
        else:
            logger.info(
                "Прямой путь между @%s и @%s не найден в пределах глубины %d",
                clean_users[0],
                clean_users[1],
                depth,
            )

    if combined["paths"]:
        # Boundary nodes of the search may not have been fetched. Read their
        # immediate senders once, without exploring the senders' profiles.
        for user in combined["paths"]:
            partial = await build_tree_graph(client, user, 1, gifts_mode,
                                            no_bots=no_bots, _gift_cache=gift_cache)
            combined["nodes"].update(partial["nodes"])
            edge_counts |= Counter(partial["edges"])
        combined["edges"] = list(edge_counts.elements())
    combined = _compact_path_graph(combined)

    logger.info(
        "Граф (path) построен: %d узлов, %d рёбер",
        len(combined["nodes"]),
        len(combined["edges"]),
    )
    return combined


def _compact_path_graph(graph: GraphData) -> GraphData:
    """Keep a spine and real leaves; discard explored trees and cross-links."""
    result = _make_graph()
    result["start"] = graph["start"]
    result["targets"] = graph["targets"]
    result["paths"] = list(graph["paths"])
    path = result["paths"]
    if not path:
        result["nodes"] = {user: graph["nodes"][user]
                           for user in [graph["start"], *graph["targets"]]}
        return result

    spine = set(path)
    pairs = {frozenset((a, b)) for a, b in zip(path, path[1:])}
    result["nodes"] = {user: graph["nodes"][user] for user in path}
    neighbors: Dict[str, Set[str]] = {user: set() for user in path}
    for src, dst, _ in graph["edges"]:
        if src in spine and dst not in spine:
            neighbors[src].add(dst)
        elif dst in spine and src not in spine:
            neighbors[dst].add(src)

    hidden = set()
    for user in path:
        added = 0
        for neighbor in sorted(neighbors[user]):
            if neighbor in result["nodes"]:
                continue  # A shared neighbor must remain a leaf, not a second route.
            if added >= PATH_LEAVES_PER_NODE or len(result["nodes"]) >= MAX_NODES_PER_GRAPH:
                hidden.add(neighbor)
                continue
            result["nodes"][neighbor] = graph["nodes"][neighbor]
            pairs.add(frozenset((user, neighbor)))
            added += 1
    result["edges"] = [(src, dst, label) for src, dst, label in graph["edges"]
                       if src != dst and frozenset((src, dst)) in pairs]
    result["hidden_leaves"] = len(hidden - set(result["nodes"]))
    return result


# ── BFS поиск кратчайшего пути ─────────────────────────────────────────────────

def _bfs_shortest_path(
    adjacency: Dict[str, Set[str]],
    start: str,
    end: str,
) -> List[str]:
    """
    Классический BFS для нахождения кратчайшего пути между двумя узлами.

    Args:
        adjacency: Список смежности (двунаправленный)
        start:     Стартовый узел
        end:       Целевой узел

    Returns:
        Список узлов пути (включая start и end), либо [] если пути нет
    """
    if start == end:
        return [start]

    if start not in adjacency:
        return []

    visited: Set[str] = {start}
    # Очередь хранит полный путь до текущего узла
    queue: deque[List[str]] = deque([[start]])

    while queue:
        path = queue.popleft()
        current = path[-1]

        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor == end:
                return path + [neighbor]

            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    return []
