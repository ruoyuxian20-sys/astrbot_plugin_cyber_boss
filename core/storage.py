"""按群隔离的 JSON 持久化：Boss 状态、本轮输出板、玩家成就、名人堂。"""

from __future__ import annotations

import json
import os
import time

from . import flavor

# 名人堂最多保留条数，防止数据文件无限膨胀
_HALL_LIMIT = 50

# 统计事件字段名与 engine 事件 kind 的映射
_KIND_STATS = {
    "hit": "hits",
    "crit": "crit",
    "dodge": "dodged",
    "counter": "countered",
    "mercy": "mercy",
    "artifact": "artifact",
}

# 成就称号的触发阈值（累计次数）
_TITLE_THRESHOLDS = {
    "filial": ("mercy", 5),  # 小猪孝子：心软 5 次
    "hospitalized": ("countered", 10),  # 住院常客：被反击 10 次
    "coder": ("artifact", 1),  # 代码术士：触发过神器
}


def empty_group() -> dict:
    return {"boss": None, "fight": None, "players": {}, "hall": [], "updated_at": 0.0}


def load_group_data(path: str) -> dict:
    """读取群数据文件；不存在或损坏时返回空结构。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty_group()
        for key, default in (
            ("boss", None),
            ("fight", None),
            ("players", {}),
            ("hall", []),
        ):
            if key not in data or data[key] is None:
                data[key] = default() if callable(default) else default
        if not isinstance(data["players"], dict):
            data["players"] = {}
        if not isinstance(data["hall"], list):
            data["hall"] = []
        return data
    except (OSError, ValueError):
        return empty_group()


def save_group_data(path: str, data: dict) -> None:
    """原子写入：先写临时文件再替换。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = os.path.join(directory, f".{os.path.basename(path)}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp_path, path)


def _player(data: dict, user_id: str, name: str, now: float) -> dict:
    players = data.setdefault("players", {})
    player = players.get(user_id)
    if player is None:
        player = {
            "name": name or "群友",
            "total_damage": 0,
            "kills": 0,
            "hits": 0,
            "crit": 0,
            "dodged": 0,
            "countered": 0,
            "mercy": 0,
            "artifact": 0,
            "titles": [],
        }
        players[user_id] = player
    if name:
        player["name"] = name
    player["updated_at"] = now
    return player


def _fight(data: dict, now: float) -> dict:
    fight = data.get("fight")
    if not isinstance(fight, dict) or not isinstance(fight.get("board"), dict):
        fight = {"started_at": now, "board": {}}
        data["fight"] = fight
    return fight


def new_titles_gained(player: dict) -> list[str]:
    """按累计统计判定成就称号；返回本次新获得的称号 key。"""
    gained = []
    titles = player.setdefault("titles", [])
    for key, (stat, need) in _TITLE_THRESHOLDS.items():
        if key not in titles and int(player.get(stat, 0)) >= need:
            titles.append(key)
            gained.append(key)
    return gained


def record_attack(
    data: dict, user_id: str, name: str, result, now: float | None = None
) -> dict:
    """把一次 attack 的结果记入本轮输出板与玩家累计统计。

    result 为 engine.AttackResult；不负责击杀结算（见 settle_kill）。
    返回更新后的玩家摘要。
    """
    now = now or time.time()
    fight = _fight(data, now)
    if not fight["board"]:
        # 本轮第一刀：以这一刀的时间作为本轮开战时间
        fight["started_at"] = now
    row = fight["board"].get(user_id)
    if row is None:
        row = {"name": name or "群友", "damage": 0, "hits": 0}
        fight["board"][user_id] = row
    if name:
        row["name"] = name
    row["damage"] = int(row.get("damage", 0)) + int(result.damage)
    row["hits"] = int(row.get("hits", 0)) + 1

    player = _player(data, user_id, name, now)
    player["total_damage"] = int(player.get("total_damage", 0)) + int(result.damage)
    stat = _KIND_STATS.get(result.kind)
    if stat:
        player[stat] = int(player.get(stat, 0)) + 1
    new_titles_gained(player)
    data["updated_at"] = now
    return dict(player)


def settle_kill(
    data: dict, killer_id: str, killer_name: str, result, now: float | None = None
) -> dict:
    """击杀结算：名人堂留名、击杀者计数、授予主力输出、清空本轮战局。

    需在 record_attack 之后、把 result.boss 写回 data["boss"] 之前调用
    （名人堂要读倒下 Boss 的代数与称号）。
    """
    now = now or time.time()
    old_boss = data.get("boss") or {}
    fight = data.get("fight") if isinstance(data.get("fight"), dict) else {"board": {}}
    board = fight.get("board") or {}
    total_damage = sum(int(row.get("damage", 0)) for row in board.values())

    entry = {
        "generation": int(old_boss.get("generation", 1)),
        "boss_name": old_boss.get("target_name", "小猪"),
        "boss_title": flavor.boss_title(int(old_boss.get("level", 1))),
        "boss_level": int(old_boss.get("level", 1)),
        "killer_id": killer_id,
        "killer_name": killer_name or "群友",
        "duration_s": max(0.0, now - float(fight.get("started_at") or now)),
        "total_damage": total_damage,
        "players": len(board),
    }
    hall = data.setdefault("hall", [])
    hall.append(entry)
    del hall[:-_HALL_LIMIT]

    killer = _player(data, killer_id, killer_name, now)
    killer["kills"] = int(killer.get("kills", 0)) + 1
    entry["killer_kills"] = int(killer["kills"])

    # 主力输出：本轮伤害榜第一（至少要有 1 点伤害）
    top_uid, top_row = None, None
    for uid, row in board.items():
        if top_row is None or int(row.get("damage", 0)) > int(top_row.get("damage", 0)):
            top_uid, top_row = uid, row
    if top_uid is not None and int(top_row.get("damage", 0)) > 0:
        entry["top_name"] = top_row.get("name", "群友")
        entry["top_damage"] = int(top_row.get("damage", 0))
        top_player = _player(data, top_uid, top_row.get("name", ""), now)
        if "top_dps" not in top_player.setdefault("titles", []):
            top_player["titles"].append("top_dps")

    data["fight"] = {"started_at": now, "board": {}}
    data["updated_at"] = now
    return entry


def ranking(data: dict, limit: int = 10) -> list[dict]:
    """本轮输出排行（伤害降序）。"""
    fight = data.get("fight")
    board = fight.get("board", {}) if isinstance(fight, dict) else {}
    rows = [
        {
            "user_id": uid,
            "name": row.get("name", "群友"),
            "damage": int(row.get("damage", 0)),
            "hits": int(row.get("hits", 0)),
        }
        for uid, row in board.items()
    ]
    rows.sort(key=lambda r: (r["damage"], r["hits"]), reverse=True)
    return rows[: max(1, limit)]


def hall_rows(data: dict, limit: int = 10) -> list[dict]:
    """名人堂（最新在前）。"""
    hall = data.get("hall") or []
    rows = list(reversed(hall))
    return rows[: max(1, limit)]


def player_report(data: dict, user_id: str) -> dict | None:
    """/boss 我 的数据视图。"""
    player = (data.get("players") or {}).get(user_id)
    if player is None:
        return None
    report = dict(player)
    report["user_id"] = user_id
    titles = []
    kills = int(player.get("kills", 0))
    if kills > 0:
        titles.append(flavor.regicide_title(kills))
    titles.extend(flavor.PLAYER_TITLES.get(t, t) for t in player.get("titles", []))
    report["display_titles"] = titles
    return report
