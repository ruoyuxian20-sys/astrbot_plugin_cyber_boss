"""按群隔离的 JSON 持久化：战局、个人养成、商店交易与名人堂。"""

from __future__ import annotations

import json
import os
import time

from . import economy, flavor

_HALL_LIMIT = 50
_KIND_STATS = {
    "hit": "hits",
    "crit": "crit",
    "dodge": "dodged",
    "counter": "countered",
    "mercy": "mercy",
    "artifact": "artifact",
}
_TITLE_THRESHOLDS = {
    "filial": ("mercy", 5),
    "hospitalized": ("countered", 10),
    "coder": ("artifact", 1),
}


def empty_group() -> dict:
    return {"boss": None, "fight": None, "players": {}, "hall": [], "updated_at": 0.0}


def _new_player(name: str, now: float) -> dict:
    return {
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
        "gold": 0,
        "marks": 0,
        "inventory": {},
        "equipped": {slot: None for slot in economy.SLOTS},
        "active_title": None,
        "armed_consumable": None,
        "updated_at": now,
    }


def _normalize_player(player: dict, name: str = "", now: float = 0.0) -> dict:
    if not isinstance(player, dict):
        return _new_player(name, now)
    defaults = _new_player(name or str(player.get("name") or "群友"), now)
    for key, default in defaults.items():
        if key not in player or player[key] is None:
            player[key] = default
    if not isinstance(player["titles"], list):
        player["titles"] = []
    if not isinstance(player["inventory"], dict):
        player["inventory"] = {}
    if not isinstance(player["equipped"], dict):
        player["equipped"] = {}
    for slot in economy.SLOTS:
        player["equipped"].setdefault(slot, None)
    for key in ("gold", "marks", "total_damage", "kills", "hits", "crit", "dodged", "countered", "mercy", "artifact"):
        try:
            player[key] = max(0, int(player.get(key, 0)))
        except (TypeError, ValueError):
            player[key] = 0
    return player


def load_group_data(path: str) -> dict:
    """读取并迁移群数据；文件损坏时返回空结构。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty_group()
    except (OSError, ValueError):
        return empty_group()
    for key, default in (("boss", None), ("fight", None), ("players", {}), ("hall", [])):
        if key not in data or data[key] is None:
            data[key] = default() if callable(default) else default
    if not isinstance(data["players"], dict):
        data["players"] = {}
    if not isinstance(data["hall"], list):
        data["hall"] = []
    for uid, player in list(data["players"].items()):
        data["players"][str(uid)] = _normalize_player(player)
        if str(uid) != uid:
            del data["players"][uid]
    return data


def save_group_data(path: str, data: dict) -> None:
    """原子写入：先写临时文件再替换。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = os.path.join(directory, f".{os.path.basename(path)}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp_path, path)


def ensure_player(data: dict, user_id: str, name: str = "群友", now: float | None = None) -> dict:
    now = time.time() if now is None else now
    players = data.setdefault("players", {})
    player = players.get(user_id)
    if player is None:
        player = _new_player(name, now)
        players[user_id] = player
    else:
        player = _normalize_player(player, name, now)
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
    gained = []
    titles = player.setdefault("titles", [])
    for key, (stat, need) in _TITLE_THRESHOLDS.items():
        if key not in titles and int(player.get(stat, 0)) >= need:
            titles.append(key)
            gained.append(key)
    return gained


def record_attack(
    data: dict,
    user_id: str,
    name: str,
    result,
    *,
    gold: int = 0,
    now: float | None = None,
) -> dict:
    """记录一次已结算攻击，包含战局输出、个人统计与金币掉落。"""
    now = time.time() if now is None else now
    fight = _fight(data, now)
    if not fight["board"]:
        fight["started_at"] = now
    row = fight["board"].get(user_id)
    if row is None:
        row = {"name": name or "群友", "damage": 0, "hits": 0, "first_attack_at": now}
        fight["board"][user_id] = row
    if name:
        row["name"] = name
    row["damage"] = int(row.get("damage", 0)) + int(result.damage)
    row["hits"] = int(row.get("hits", 0)) + 1
    row.setdefault("first_attack_at", now)

    player = ensure_player(data, user_id, name, now)
    player["total_damage"] += int(result.damage)
    player["gold"] += max(0, int(gold))
    stat = _KIND_STATS.get(result.kind)
    if stat:
        player[stat] += 1
    new_titles_gained(player)
    data["updated_at"] = now
    return dict(player)


def consume_armed_consumable(player: dict) -> dict | None:
    item_id = str(player.get("armed_consumable") or "")
    item = economy.product(item_id)
    if not item or item["kind"] != "consumable":
        player["armed_consumable"] = None
        return None
    inventory = player.setdefault("inventory", {})
    if int(inventory.get(item_id, 0)) <= 0:
        player["armed_consumable"] = None
        return None
    inventory[item_id] -= 1
    if inventory[item_id] <= 0:
        inventory.pop(item_id, None)
    player["armed_consumable"] = None
    return item


def _top_row(board: dict) -> tuple[str | None, dict | None]:
    candidates = [(uid, row) for uid, row in board.items() if int(row.get("damage", 0)) > 0]
    if not candidates:
        return None, None
    candidates.sort(
        key=lambda entry: (
            -int(entry[1].get("damage", 0)),
            -int(entry[1].get("hits", 0)),
            float(entry[1].get("first_attack_at", 0.0)),
            str(entry[0]),
        )
    )
    return candidates[0]


def settle_kill(
    data: dict, killer_id: str, killer_name: str, result, now: float | None = None
) -> dict:
    """击杀结算：荣誉、印记、名人堂与本轮战局重置。"""
    now = time.time() if now is None else now
    old_boss = data.get("boss") or {}
    fight = data.get("fight") if isinstance(data.get("fight"), dict) else {"board": {}}
    board = fight.get("board") or {}
    total_damage = sum(int(row.get("damage", 0)) for row in board.values())
    top_uid, top_row = _top_row(board)

    killer = ensure_player(data, killer_id, killer_name, now)
    killer["kills"] += 1
    if top_uid is not None:
        top_player = ensure_player(data, top_uid, str(top_row.get("name") or "群友"), now)
        if "top_dps" not in top_player["titles"]:
            top_player["titles"].append("top_dps")
    double_crown = top_uid == killer_id and top_uid is not None
    if double_crown and "double_crown" not in killer["titles"]:
        killer["titles"].append("double_crown")

    rewards = {}
    for uid, row in board.items():
        damage = int(row.get("damage", 0))
        if damage <= 0:
            continue
        player = ensure_player(data, uid, str(row.get("name") or "群友"), now)
        marks = economy.mark_reward(player, damage, total_damage, is_mvp=uid == top_uid, is_killer=uid == killer_id)
        player["marks"] += marks
        rewards[uid] = {
            "name": player["name"],
            "marks": marks,
            "damage": damage,
            "contribution": damage / total_damage if total_damage else 0.0,
        }

    entry = {
        "generation": int(old_boss.get("generation", 1)),
        "boss_name": old_boss.get("target_name", "小猪"),
        "boss_title": flavor.boss_title(int(old_boss.get("level", 1))),
        "boss_level": int(old_boss.get("level", 1)),
        "killer_id": killer_id,
        "killer_name": killer_name or "群友",
        "killer_kills": int(killer["kills"]),
        "duration_s": max(0.0, now - float(fight.get("started_at") or now)),
        "total_damage": total_damage,
        "players": len(board),
        "top_id": top_uid,
        "top_name": top_row.get("name", "群友") if top_row else "",
        "top_damage": int(top_row.get("damage", 0)) if top_row else 0,
        "double_crown": double_crown,
        "rewards": rewards,
    }
    hall = data.setdefault("hall", [])
    hall.append(entry)
    del hall[:-_HALL_LIMIT]
    data["fight"] = {"started_at": now, "board": {}}
    data["updated_at"] = now
    return entry


def buy_item(data: dict, user_id: str, name: str, item_id: str, quantity: int, now: float | None = None) -> tuple[bool, str, dict | None]:
    item, resolve_error = economy.resolve_product(item_id)
    if item is None:
        return False, resolve_error or "找不到这个商品。", None
    try:
        quantity = max(1, int(quantity))
    except (TypeError, ValueError):
        return False, "数量必须是正整数。", None
    if item["kind"] == "equipment":
        quantity = 1
    player = ensure_player(data, user_id, name, now)
    if economy.hunter_rank(player["total_damage"])["level"] < item["rank"]:
        return False, f"需要猎手 {item['rank']} 阶才能购买。", None
    inventory = player["inventory"]
    if item["kind"] == "equipment" and int(inventory.get(item["id"], 0)) > 0:
        return False, "这件装备已经拥有，不能重复购买。", None
    if item["kind"] == "consumable" and int(inventory.get(item["id"], 0)) + quantity > 99:
        return False, "同一种消耗品最多持有 99 个。", None
    cost = item["price"] * quantity
    wallet = item["currency"]
    if int(player.get(wallet, 0)) < cost:
        currency_name = "金币" if wallet == "gold" else "猪神印记"
        return False, f"{currency_name}不足，需要 {cost}。", None
    player[wallet] -= cost
    inventory[item["id"]] = int(inventory.get(item["id"], 0)) + quantity
    data["updated_at"] = time.time() if now is None else now
    return True, f"购买成功：{item['name']} ×{quantity}", item


def equip_item(data: dict, user_id: str, name: str, item_id: str, now: float | None = None) -> tuple[bool, str, dict | None]:
    item = economy.product(item_id)
    if item is None or item["kind"] != "equipment":
        return False, "只能装备商店中的装备。", None
    player = ensure_player(data, user_id, name, now)
    if int(player["inventory"].get(item["id"], 0)) <= 0:
        return False, "背包中没有这件装备。", None
    player["equipped"][item["slot"]] = item["id"]
    return True, f"已装备 {item['name']} 到{economy.SLOT_NAMES[item['slot']]}栏。", item


def unequip_item(data: dict, user_id: str, name: str, slot: str, now: float | None = None) -> tuple[bool, str]:
    aliases = {"武器": "weapon", "副手": "offhand", "护具": "armor", "饰品": "accessory"}
    slot = aliases.get(str(slot), str(slot).lower())
    if slot not in economy.SLOTS:
        return False, "栏位应为：武器、副手、护具、饰品。"
    player = ensure_player(data, user_id, name, now)
    if not player["equipped"].get(slot):
        return False, f"{economy.SLOT_NAMES[slot]}栏没有装备。"
    player["equipped"][slot] = None
    return True, f"已卸下{economy.SLOT_NAMES[slot]}栏装备。"


def arm_consumable(data: dict, user_id: str, name: str, item_id: str, now: float | None = None) -> tuple[bool, str, dict | None]:
    item = economy.product(item_id)
    if item is None or item["kind"] != "consumable":
        return False, "只能武装消耗品。", None
    player = ensure_player(data, user_id, name, now)
    if int(player["inventory"].get(item["id"], 0)) <= 0:
        return False, "背包中没有这个消耗品。", None
    player["armed_consumable"] = item["id"]
    return True, f"已武装 {item['name']}；会在下一次实际结算的 /砍猪 中消耗。", item


def set_active_title(data: dict, user_id: str, name: str, title_id: str, now: float | None = None) -> tuple[bool, str]:
    player = ensure_player(data, user_id, name, now)
    title_id = str(title_id).lower()
    if title_id not in economy.available_titles(player):
        return False, "该称号尚未解锁。"
    player["active_title"] = title_id
    return True, f"已佩戴称号「{economy.title_name(title_id, player)}」。"


def ranking(data: dict, limit: int = 10) -> list[dict]:
    fight = data.get("fight")
    board = fight.get("board", {}) if isinstance(fight, dict) else {}
    rows = [
        {"user_id": uid, "name": row.get("name", "群友"), "damage": int(row.get("damage", 0)), "hits": int(row.get("hits", 0)), "first_attack_at": float(row.get("first_attack_at", 0.0))}
        for uid, row in board.items()
    ]
    rows.sort(key=lambda row: (-row["damage"], -row["hits"], row["first_attack_at"], row["user_id"]))
    return rows[: max(1, limit)]


def hall_rows(data: dict, limit: int = 10) -> list[dict]:
    return list(reversed(data.get("hall") or []))[: max(1, limit)]


def player_report(data: dict, user_id: str, name: str = "群友") -> dict:
    player = (data.get("players") or {}).get(user_id)
    if player is None:
        player = _new_player(name, 0.0)
    else:
        player = _normalize_player(dict(player), name)
    report = dict(player)
    report["user_id"] = user_id
    report["rank"] = economy.hunter_rank(report["total_damage"])
    report["display_titles"] = [
        economy.title_name(title_id, report) for title_id in economy.available_titles(report)
    ]
    report["title_options"] = [
        {"id": title_id, "name": economy.title_name(title_id, report), "description": economy.TITLE_META[title_id][1]}
        for title_id in economy.available_titles(report)
    ]
    report["active_title_name"] = economy.title_name(report["active_title"], report) if report.get("active_title") else "未佩戴"
    report["modifiers"] = economy.combat_modifiers(report)
    return report
