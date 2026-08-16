"""战斗引擎：一次攻击的判定与 Boss 的升级复活。纯逻辑，注入 rng，不落盘。"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import flavor

# 事件权重表（合计 100）：普通 / 暴击 / 闪避 / 反击 / 心软 / 神器
_WEIGHTS_NORMAL = (
    ("hit", 60.0),
    ("crit", 15.0),
    ("dodge", 10.0),
    ("counter", 7.0),
    ("mercy", 2.5),
    ("artifact", 0.5),
)
# 狂暴期：反击概率翻倍，普通命中让位
_WEIGHTS_ENRAGED = (
    ("hit", 50.0),
    ("crit", 15.0),
    ("dodge", 8.0),
    ("counter", 14.0),
    ("mercy", 2.5),
    ("artifact", 0.5),
)

_ENRAGE_RATIO = 0.20  # 血量 <= 20% 进入狂暴


@dataclass
class AttackResult:
    """一次攻击的完整判定结果。boss 字段是结算后的新 Boss（击杀时已升级复活）。"""

    kind: str  # hit | crit | dodge | counter | mercy | artifact
    damage: int = 0  # 对 Boss 造成的伤害
    heal: int = 0  # Boss 的回血量（心软）
    line: str = ""  # 主文案（已带 Boss/玩家昵称）
    killed: bool = False
    boss: dict = field(default_factory=dict)
    enraged_before: bool = False  # 出手时 Boss 是否狂暴


def new_boss(
    target_id: str = "",
    target_name: str = "群主",
    initial_hp: int = 10000,
    generation: int = 1,
) -> dict:
    """创建一个 1 级 Boss。generation 继承群内总代数（换养目标不清代数）。"""
    hp = max(100, int(initial_hp))
    return {
        "target_id": str(target_id or ""),
        "target_name": (target_name or "群主").strip() or "群主",
        "level": 1,
        "max_hp": hp,
        "hp": hp,
        "generation": int(generation),
    }


def boss_display_name(boss: dict) -> str:
    return boss.get("target_name") or "群主"


def is_enraged(boss: dict) -> bool:
    max_hp = max(1, int(boss.get("max_hp", 1)))
    return int(boss.get("hp", 0)) <= max_hp * _ENRAGE_RATIO


def _roll_kind(rng: random.Random, enraged: bool) -> str:
    table = _WEIGHTS_ENRAGED if enraged else _WEIGHTS_NORMAL
    total = sum(w for _, w in table)
    point = rng.random() * total
    acc = 0.0
    for kind, weight in table:
        acc += weight
        if point < acc:
            return kind
    return table[-1][0]


def attack(
    rng: random.Random,
    boss: dict,
    player_name: str,
    *,
    hp_growth: float = 1.2,
) -> AttackResult:
    """砍一刀：判定事件、结算伤害，血量归零时当场升级复活。

    不修改入参 boss，返回的新 boss 由调用方落库。
    """
    player = player_name or "群友"
    target = boss_display_name(boss)
    enraged = is_enraged(boss)
    kind = _roll_kind(rng, enraged)

    hp = int(boss.get("hp", 0))
    max_hp = max(1, int(boss.get("max_hp", 1)))
    damage = 0
    heal = 0

    if kind == "hit":
        damage = rng.randint(15, 75)
        line = rng.choice(flavor.HIT_QUIPS).format(player=player, boss=target)
    elif kind == "crit":
        base = rng.randint(15, 75)
        damage = int(base * rng.uniform(2.0, 3.0))
        weapon = rng.choice(flavor.CRIT_WEAPONS)
        line = (
            f"⭐ 暴击！{player} 拿起【{weapon['name']}】{weapon['verb']}，"
            f"{target} 眼冒金星"
        )
    elif kind == "dodge":
        line = f"💨 {rng.choice(flavor.DODGE_LINES).format(player=player, boss=target)}"
    elif kind == "counter":
        line = (
            f"🩹 {rng.choice(flavor.COUNTER_LINES).format(player=player, boss=target)}"
        )
    elif kind == "mercy":
        heal = rng.randint(20, 80)
        line = f"💗 心软！{rng.choice(flavor.MERCY_LINES).format(player=player, boss=target)}"
    else:  # artifact
        damage = 500 * max(1, int(boss.get("level", 1)))
        line = f"⚡ 神器降世！{rng.choice(flavor.ARTIFACT_LINES).format(player=player, boss=target)}"

    hp = max(0, min(max_hp, hp + heal) - damage)
    killed = hp <= 0

    new = dict(boss)
    if killed:
        growth = max(1.05, float(hp_growth))
        new["level"] = int(boss.get("level", 1)) + 1
        new["max_hp"] = max(100, round(max_hp * growth))
        new["hp"] = new["max_hp"]
        new["generation"] = int(boss.get("generation", 1)) + 1
    else:
        new["hp"] = hp

    return AttackResult(
        kind=kind,
        damage=damage,
        heal=heal,
        line=line,
        killed=killed,
        boss=new,
        enraged_before=enraged,
    )
