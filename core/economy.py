"""商店、装备、称号与掉落规则。所有规则均为纯逻辑，不依赖 AstrBot。"""

from __future__ import annotations

import math
from typing import Any

SLOTS = ("weapon", "offhand", "armor", "accessory")
SLOT_NAMES = {
    "weapon": "武器",
    "offhand": "副手",
    "armor": "护具",
    "accessory": "饰品",
}
RANKS = (
    (1, "见习猎手", 0),
    (2, "熟练猎手", 2000),
    (3, "精英猎手", 8000),
    (4, "传奇猎手", 25000),
    (5, "猪神猎手", 70000),
)


def _product(
    item_id: str,
    name: str,
    kind: str,
    currency: str,
    price: int,
    rank: int,
    description: str,
    *,
    slot: str | None = None,
    effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "kind": kind,
        "currency": currency,
        "price": price,
        "rank": rank,
        "description": description,
        "slot": slot,
        "effects": effects or {},
    }


# 8 个消耗品 + 24 件金币装备 + 24 件印记装备。商品 ID 是持久化接口，发布后不复用。
PRODUCTS = (
    _product("C01", "磨刀石", "consumable", "gold", 5, 1, "下次攻击额外造成 35 点伤害", effects={"flat_damage": 35}),
    _product("C02", "暴走冰红茶", "consumable", "gold", 9, 1, "下次攻击伤害 +35%", effects={"damage_pct": 0.35}),
    _product("C03", "暴击辣条", "consumable", "gold", 14, 2, "下次攻击额外 +20% 暴击机会", effects={"crit_bonus": 0.20}),
    _product("C04", "住院免责卡", "consumable", "gold", 12, 1, "下次反击必定被格挡", effects={"counter_block": 1.0}),
    _product("C05", "幸运猪蹄", "consumable", "gold", 11, 2, "下次攻击金币掉落翻倍", effects={"gold_multiplier": 2.0}),
    _product("C06", "破甲辣条", "consumable", "gold", 18, 2, "Boss 狂暴时，下次攻击伤害额外 +75%", effects={"low_hp_damage_pct": 0.75}),
    _product("C07", "已读撤回券", "consumable", "gold", 20, 3, "下次闪避时重掷一次事件", effects={"dodge_reroll": 1.0}),
    _product("C08", "祖传 main.py", "consumable", "gold", 28, 3, "下次攻击额外 +8% 神器机会", effects={"artifact_bonus": 0.08}),
    _product("GW1", "铁皮菜刀", "equipment", "gold", 6, 1, "伤害 +8", slot="weapon", effects={"flat_damage": 8}),
    _product("GW2", "加班太刀", "equipment", "gold", 36, 2, "伤害 +12%", slot="weapon", effects={"damage_pct": 0.12}),
    _product("GW3", "红温电锯", "equipment", "gold", 110, 3, "暴击机会 +8%", slot="weapon", effects={"crit_bonus": 0.08}),
    _product("GO1", "不粘锅盖", "equipment", "gold", 10, 1, "10% 概率触发连击", slot="offhand", effects={"combo_chance": 0.10}),
    _product("GO2", "缓存 U 盘", "equipment", "gold", 42, 2, "神器机会 +1%", slot="offhand", effects={"artifact_bonus": 0.01}),
    _product("GO3", "撤回键盘", "equipment", "gold", 118, 3, "25% 概率重掷闪避", slot="offhand", effects={"dodge_reroll": 0.25}),
    _product("GA1", "纸箱护甲", "equipment", "gold", 9, 1, "10% 概率格挡反击", slot="armor", effects={"counter_block": 0.10}),
    _product("GA2", "病号服", "equipment", "gold", 38, 2, "住院时间 -25%", slot="armor", effects={"hospital_reduction": 0.25}),
    _product("GA3", "玻璃心甲", "equipment", "gold", 105, 3, "心软事件额外获得 2 金币", slot="armor", effects={"mercy_gold": 2}),
    _product("GX1", "红包挂件", "equipment", "gold", 12, 1, "金币掉落 +10%", slot="accessory", effects={"gold_bonus": 0.10}),
    _product("GX2", "红温温度计", "equipment", "gold", 45, 2, "Boss 狂暴时伤害 +15%", slot="accessory", effects={"low_hp_damage_pct": 0.15}),
    _product("GX3", "金币磁铁", "equipment", "gold", 120, 3, "金币掉落 +20%", slot="accessory", effects={"gold_bonus": 0.20}),
    _product("MW1", "猪神断头台", "equipment", "marks", 12, 3, "伤害 +18%，暴击伤害额外 +50%", slot="weapon", effects={"damage_pct": 0.18, "crit_damage_pct": 0.50}),
    _product("MW2", "深海处刑刀", "equipment", "marks", 26, 4, "Boss 狂暴时伤害 +50%", slot="weapon", effects={"low_hp_damage_pct": 0.50}),
    _product("MW3", "永恒猪神刃", "equipment", "marks", 44, 5, "神器伤害 +35%，伤害 +10%", slot="weapon", effects={"artifact_damage_pct": 0.35, "damage_pct": 0.10}),
    _product("MO1", "连击机械臂", "equipment", "marks", 12, 3, "20% 概率触发连击", slot="offhand", effects={"combo_chance": 0.20}),
    _product("MO2", "热更新硬盘", "equipment", "marks", 26, 4, "神器机会 +3%", slot="offhand", effects={"artifact_bonus": 0.03}),
    _product("MO3", "时光回溯器", "equipment", "marks", 44, 5, "闪避时必定重掷一次事件", slot="offhand", effects={"dodge_reroll": 1.0}),
    _product("MA1", "猪神护盾", "equipment", "marks", 12, 3, "35% 概率格挡反击", slot="armor", effects={"counter_block": 0.35}),
    _product("MA2", "反击回收甲", "equipment", "marks", 26, 4, "被反击时仍获得额外 3 金币", slot="armor", effects={"counter_gold": 3}),
    _product("MA3", "逆转病房", "equipment", "marks", 44, 5, "心软回血量 -50%，住院时间 -35%", slot="armor", effects={"mercy_heal_pct": -0.50, "hospital_reduction": 0.35}),
    _product("MX1", "印记罗盘", "equipment", "marks", 12, 3, "击杀参与奖励额外 +1 印记", slot="accessory", effects={"mark_bonus": 1}),
    _product("MX2", "双冠徽章", "equipment", "marks", 26, 4, "获得 MVP 时额外 +2 印记", slot="accessory", effects={"mvp_mark_bonus": 2}),
    _product("MX3", "赛博聚宝盆", "equipment", "marks", 44, 5, "金币掉落 +30%，补刀额外 +1 印记", slot="accessory", effects={"gold_bonus": 0.30, "killer_mark_bonus": 1}),
    _product("GW4", "加粗铅笔", "equipment", "gold", 16, 1, "伤害 +14", slot="weapon", effects={"flat_damage": 14}),
    _product("GW5", "错题本长枪", "equipment", "gold", 62, 2, "暴击伤害额外 +25%", slot="weapon", effects={"crit_damage_pct": 0.25}),
    _product("GW6", "周报粉碎机", "equipment", "gold", 155, 3, "Boss 狂暴时伤害 +25%", slot="weapon", effects={"low_hp_damage_pct": 0.25}),
    _product("MW4", "代码行刑剑", "equipment", "marks", 14, 3, "伤害 +30", slot="weapon", effects={"flat_damage": 30}),
    _product("MW5", "红温斩舰刀", "equipment", "marks", 30, 4, "暴击机会 +12%", slot="weapon", effects={"crit_bonus": 0.12}),
    _product("MW6", "爆栈终结者", "equipment", "marks", 52, 5, "Boss 狂暴时伤害 +40%", slot="weapon", effects={"low_hp_damage_pct": 0.40}),
    _product("GO4", "弹簧鼠标", "equipment", "gold", 16, 1, "8% 概率触发连击", slot="offhand", effects={"combo_chance": 0.08}),
    _product("GO5", "404护符", "equipment", "gold", 64, 2, "神器伤害额外 +15%", slot="offhand", effects={"artifact_damage_pct": 0.15}),
    _product("GO6", "语音转文字器", "equipment", "gold", 160, 3, "45% 概率重掷闪避", slot="offhand", effects={"dodge_reroll": 0.45}),
    _product("MO4", "量子回形针", "equipment", "marks", 14, 3, "15% 概率触发连击", slot="offhand", effects={"combo_chance": 0.15}),
    _product("MO5", "祖传路由器", "equipment", "marks", 30, 4, "神器机会 +2.5%", slot="offhand", effects={"artifact_bonus": 0.025}),
    _product("MO6", "群聊时间机", "equipment", "marks", 52, 5, "75% 概率重掷闪避", slot="offhand", effects={"dodge_reroll": 0.75}),
    _product("GA4", "工牌护心镜", "equipment", "gold", 15, 1, "住院时间 -15%", slot="armor", effects={"hospital_reduction": 0.15}),
    _product("GA5", "免打扰斗篷", "equipment", "gold", 60, 2, "20% 概率格挡反击", slot="armor", effects={"counter_block": 0.20}),
    _product("GA6", "摸鱼披风", "equipment", "gold", 150, 3, "被反击时额外获得 2 金币", slot="armor", effects={"counter_gold": 2}),
    _product("MA4", "重启护甲", "equipment", "marks", 14, 3, "25% 概率格挡反击", slot="armor", effects={"counter_block": 0.25}),
    _product("MA5", "降噪病房", "equipment", "marks", 30, 4, "住院时间 -40%", slot="armor", effects={"hospital_reduction": 0.40}),
    _product("MA6", "群公告防爆服", "equipment", "marks", 52, 5, "心软回血量 -30%，反击额外 +4 金币", slot="armor", effects={"mercy_heal_pct": -0.30, "counter_gold": 4}),
    _product("GX4", "签到日历", "equipment", "gold", 18, 1, "金币掉落 +8%", slot="accessory", effects={"gold_bonus": 0.08}),
    _product("GX5", "输出记账本", "equipment", "gold", 66, 2, "获得 MVP 时额外 +1 印记", slot="accessory", effects={"mvp_mark_bonus": 1}),
    _product("GX6", "深夜咖啡券", "equipment", "gold", 165, 3, "神器机会 +1.5%", slot="accessory", effects={"artifact_bonus": 0.015}),
    _product("MX4", "荣耀勋章", "equipment", "marks", 14, 3, "补刀时额外 +1 印记", slot="accessory", effects={"killer_mark_bonus": 1}),
    _product("MX5", "暴富小金猪", "equipment", "marks", 30, 4, "金币掉落 +25%", slot="accessory", effects={"gold_bonus": 0.25}),
    _product("MX6", "群友应援灯", "equipment", "marks", 52, 5, "参与击杀额外 +1 印记，MVP 额外 +1 印记", slot="accessory", effects={"mark_bonus": 1, "mvp_mark_bonus": 1}),
)
PRODUCT_BY_ID = {item["id"]: item for item in PRODUCTS}
PRODUCTS_BY_NAME = {}
for _item in PRODUCTS:
    PRODUCTS_BY_NAME.setdefault(_item["name"], []).append(_item)

TITLE_META = {
    "regicide": ("弑猪者", "每次击杀增强伤害，最高 +10%", "damage_pct"),
    "top_dps": ("主力输出", "暴击机会 +8%", "crit_bonus"),
    "double_crown": ("双冠斩首", "金币掉落 +15%", "gold_bonus"),
    "filial": ("小猪孝子", "心软时额外获得 3 金币", "mercy_gold"),
    "hospitalized": ("住院常客", "住院时间 -20%", "hospital_reduction"),
    "coder": ("代码术士", "神器伤害 +20%", "artifact_damage_pct"),
}


def hunter_rank(total_damage: int) -> dict[str, Any]:
    total = max(0, int(total_damage))
    current = RANKS[0]
    next_rank = None
    for rank in RANKS:
        if total >= rank[2]:
            current = rank
        else:
            next_rank = rank
            break
    return {"level": current[0], "name": current[1], "required_damage": current[2], "next_damage": next_rank[2] if next_rank else None}


def resolve_product(reference: str) -> tuple[dict[str, Any] | None, str | None]:
    """按稳定 ID 或精确名称查找商品；名称歧义时要求使用 ID。"""
    raw = str(reference or "").strip()
    if not raw:
        return None, "请提供商品 ID 或完整名称。"
    item = PRODUCT_BY_ID.get(raw.upper())
    if item:
        return item, None
    matches = PRODUCTS_BY_NAME.get(raw, [])
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "商品名称不唯一，请使用商品 ID。"
    return None, "找不到这个商品 ID 或名称。"


def product(reference: str) -> dict[str, Any] | None:
    return resolve_product(reference)[0]


def product_pages(page_size: int = 8) -> int:
    return max(1, math.ceil(len(PRODUCTS) / page_size))


def shop_page(player: dict, page: int = 1, page_size: int = 8) -> tuple[list[dict], int, int]:
    pages = product_pages(page_size)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = min(max(1, page), pages)
    start = (page - 1) * page_size
    owned = player.get("inventory", {}) if isinstance(player, dict) else {}
    rank = hunter_rank(int((player or {}).get("total_damage", 0)))["level"]
    rows = []
    for item in PRODUCTS[start : start + page_size]:
        row = dict(item)
        row["owned"] = int(owned.get(item["id"], 0))
        row["available"] = rank >= item["rank"]
        rows.append(row)
    return rows, page, pages


def _annotate_shop_items(player: dict, items: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict]:
    owned = player.get("inventory", {}) if isinstance(player, dict) else {}
    rank = hunter_rank(int((player or {}).get("total_damage", 0)))["level"]
    rows = []
    for item in items:
        row = dict(item)
        row["owned"] = int(owned.get(item["id"], 0))
        row["available"] = rank >= item["rank"]
        row["affordable"] = int((player or {}).get(item["currency"], 0)) >= item["price"]
        rows.append(row)
    return rows


def shop_sections(player: dict, view: str = "全览") -> tuple[str, list[tuple[str, list[dict]]]]:
    """返回商店的全览或单次筛选结果，不要求用户翻页。"""
    raw = str(view or "全览").strip().lower()
    aliases = {
        "": "全览", "all": "全览", "全部": "全览", "可买": "可买", "可购买": "可买",
        "weapon": "武器", "offhand": "副手", "armor": "护具", "accessory": "饰品",
        "consumable": "消耗品", "gold": "金币", "marks": "印记",
    }
    selected = aliases.get(raw, raw)
    if selected == "全览":
        sections = [("消耗品", [item for item in PRODUCTS if item["kind"] == "consumable"])]
        for slot in SLOTS:
            sections.append((f"{SLOT_NAMES[slot]} · 金币装备", [item for item in PRODUCTS if item["slot"] == slot and item["currency"] == "gold"]))
            sections.append((f"{SLOT_NAMES[slot]} · 印记装备", [item for item in PRODUCTS if item["slot"] == slot and item["currency"] == "marks"]))
        return "小猪商店 · 全目录", [(name, _annotate_shop_items(player, items)) for name, items in sections]
    if selected == "可买":
        rows = [row for row in _annotate_shop_items(player, PRODUCTS) if row["available"] and row["affordable"]]
        return "小猪商店 · 当前可购买", [("可购买商品", rows)]
    if selected in SLOT_NAMES:
        rows = [item for item in PRODUCTS if item["slot"] == selected]
        return f"小猪商店 · {SLOT_NAMES[selected]}", [(SLOT_NAMES[selected], _annotate_shop_items(player, rows))]
    if selected == "消耗品":
        rows = [item for item in PRODUCTS if item["kind"] == "consumable"]
        return "小猪商店 · 消耗品", [("消耗品", _annotate_shop_items(player, rows))]
    if selected in ("金币", "印记"):
        currency = "gold" if selected == "金币" else "marks"
        rows = [item for item in PRODUCTS if item["currency"] == currency]
        return f"小猪商店 · {selected}", [(f"{selected}商品", _annotate_shop_items(player, rows))]
    return "", []


def title_name(title_id: str, player: dict | None = None) -> str:
    if title_id == "regicide":
        return f"弑猪者Lv{max(1, int((player or {}).get('kills', 0)))}"
    return TITLE_META.get(title_id, (title_id, "", ""))[0]


def available_titles(player: dict) -> list[str]:
    titles = list(player.get("titles", []))
    if int(player.get("kills", 0)) > 0:
        titles.insert(0, "regicide")
    return [title for title in titles if title in TITLE_META]


def title_effects(player: dict) -> dict[str, float]:
    active = str(player.get("active_title") or "")
    if active not in available_titles(player):
        return {}
    if active == "regicide":
        return {"damage_pct": min(0.10, 0.02 + 0.01 * int(player.get("kills", 0)))}
    effect_key = TITLE_META[active][2]
    values = {
        "crit_bonus": 0.08,
        "gold_bonus": 0.15,
        "mercy_gold": 3,
        "hospital_reduction": 0.20,
        "artifact_damage_pct": 0.20,
    }
    return {effect_key: values[effect_key]}


def _add_effects(target: dict[str, float], effects: dict[str, Any]) -> None:
    for key, value in effects.items():
        if isinstance(value, (int, float)):
            target[key] = target.get(key, 0.0) + value


def combat_modifiers(player: dict) -> dict[str, float]:
    """聚合四栏装备、一个称号和已武装消耗品，并执行数值上限。"""
    modifiers: dict[str, float] = {}
    inventory = player.get("inventory", {})
    for item_id in (player.get("equipped") or {}).values():
        item = product(item_id)
        if item and int(inventory.get(item_id, 0)) > 0:
            _add_effects(modifiers, item["effects"])
    _add_effects(modifiers, title_effects(player))
    armed = product(player.get("armed_consumable") or "")
    if armed and armed["kind"] == "consumable" and int(inventory.get(armed["id"], 0)) > 0:
        _add_effects(modifiers, armed["effects"])
        modifiers["armed"] = 1.0
    for key, cap in {
        "flat_damage": 60,
        "damage_pct": 0.70,
        "crit_bonus": 0.35,
        "crit_damage_pct": 0.50,
        "artifact_bonus": 0.13,
        "counter_block": 1.0,
        "gold_bonus": 0.30,
        "combo_chance": 0.35,
        "hospital_reduction": 0.60,
        "low_hp_damage_pct": 0.90,
    }.items():
        modifiers[key] = min(cap, modifiers.get(key, 0.0))
    return modifiers


def gold_drop(damage: int, kind: str, modifiers: dict[str, float]) -> int:
    gold = 1 + min(9, max(0, int(damage)) // 50)
    if kind == "mercy":
        gold += int(modifiers.get("mercy_gold", 0))
    if kind == "counter":
        gold += int(modifiers.get("counter_gold", 0))
    gold = math.floor(gold * (1 + modifiers.get("gold_bonus", 0.0)))
    return max(1, int(gold * modifiers.get("gold_multiplier", 1.0)))


def contribution_bonus(damage: int, total_damage: int) -> int:
    if damage <= 0 or total_damage <= 0:
        return 0
    ratio = damage / total_damage
    if ratio >= 0.50:
        return 4
    if ratio >= 0.30:
        return 3
    if ratio >= 0.15:
        return 2
    if ratio >= 0.05:
        return 1
    return 0


def mark_reward(player: dict, damage: int, total_damage: int, *, is_mvp: bool, is_killer: bool) -> int:
    if damage <= 0:
        return 0
    modifiers = combat_modifiers(player)
    marks = 1 + contribution_bonus(damage, total_damage) + int(modifiers.get("mark_bonus", 0))
    if is_mvp:
        marks += 4 + int(modifiers.get("mvp_mark_bonus", 0))
    if is_killer:
        marks += 3 + int(modifiers.get("killer_mark_bonus", 0))
    return marks


def effect_summary(modifiers: dict[str, float]) -> str:
    labels = []
    if modifiers.get("flat_damage"):
        labels.append(f"伤害+{int(modifiers['flat_damage'])}")
    if modifiers.get("damage_pct"):
        labels.append(f"伤害+{modifiers['damage_pct']:.0%}")
    if modifiers.get("crit_bonus"):
        labels.append(f"暴击+{modifiers['crit_bonus']:.0%}")
    if modifiers.get("gold_bonus"):
        labels.append(f"金币+{modifiers['gold_bonus']:.0%}")
    if modifiers.get("counter_block"):
        labels.append(f"格挡+{modifiers['counter_block']:.0%}")
    return " · ".join(labels) or "暂无战斗加成"
