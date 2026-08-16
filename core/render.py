"""输出格式化：文本血条、战报文案、可选 T2I 图卡 HTML。"""

from __future__ import annotations

import html as html_escape
import random

from . import flavor

_BAR_WIDTH = 10


def fmt_duration(seconds: float) -> str:
    """人类可读时长。"""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} 秒"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} 分 {s} 秒"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} 小时 {m} 分"
    d, h = divmod(h, 24)
    return f"{d} 天 {h} 小时"


def text_bar(hp: int, max_hp: int, width: int = _BAR_WIDTH) -> str:
    """文本血条：██████░░░░ 60.0%"""
    max_hp = max(1, int(max_hp))
    hp = max(0, min(max_hp, int(hp)))
    filled = round(width * hp / max_hp)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {hp / max_hp:.0%}"


def boss_headline(boss: dict) -> str:
    """Boss 一行简介。"""
    name = flavor.boss_title(int(boss.get("level", 1)))
    return (
        f"⚔️ {boss.get('target_name', '群主')} · {name}"
        f" · Lv{int(boss.get('level', 1))} · 第{int(boss.get('generation', 1))}代"
    )


def format_attack_text(result, boss: dict) -> str:
    """一次 /砍 的纯文本输出（不含击杀播报，那由 format_kill_text 负责）。"""
    name = boss.get("target_name", "群主")
    hp, max_hp = int(boss["hp"]), int(boss["max_hp"])
    lines = [result.line]
    if result.kind in ("hit", "crit", "artifact"):
        lines.append(f"💥 对 {name} 造成 {result.damage} 点伤害")
    elif result.kind == "dodge":
        lines.append("💨 这一刀落了空")
    elif result.kind == "counter":
        lines.append("🩹 你被反击了，需要住院观察")
    elif result.kind == "mercy":
        lines.append(f"💗 {name} 回了 {result.heal} 口血")
    lines.append(text_bar(hp, max_hp))
    if not result.killed and hp <= max_hp * 0.2:
        lines.append(random.choice(flavor.ENRAGE_LINES).format(boss=name))
    return "\n".join(lines)


def format_kill_text(
    result,
    boss_after: dict,
    player_name: str,
    entry: dict,
    rng: random.Random | None = None,
) -> str:
    """击杀播报：倒下 + 战报 + 复活。主力输出信息来自 settle_kill 写入的 entry。"""
    rng = rng or random.Random()
    old_name = entry.get("boss_name", "群主")
    lines = [
        rng.choice(flavor.KILL_HEADER).format(boss=old_name),
        (
            f"🗡️ 最后一刀由 {player_name or '群友'} 补上"
            f" →「{flavor.regicide_title(int(entry.get('killer_kills', 1)))}」"
        ),
        (
            f"📊 本轮战报：总输出 {entry.get('total_damage', 0)} 点"
            f" · 参战 {entry.get('players', 0)} 人"
            f" · 耗时 {fmt_duration(entry.get('duration_s', 0.0))}"
        ),
    ]
    if entry.get("top_name"):
        lines.append(
            f"🥇 主力输出：{entry['top_name']}（{entry.get('top_damage', 0)} 点）"
        )
    new_title = flavor.boss_title(int(boss_after.get("level", 2)))
    new_name = boss_after.get("target_name", "群主")
    lines.append(rng.choice(flavor.REVIVE_LINES).format(boss=new_name))
    lines.append(
        f"✨ Lv{int(boss_after.get('level', 2))} · {new_title}"
        f" · 血量 {int(boss_after['max_hp'])}"
    )
    return "\n".join(lines)


def format_status_text(
    boss: dict, fight: dict | None, rows: list[dict], now: float
) -> str:
    """/boss 状态 输出。"""
    hp, max_hp = int(boss["hp"]), int(boss["max_hp"])
    lines = [boss_headline(boss), f"血量 {text_bar(hp, max_hp)}（{hp}/{max_hp}）"]
    if hp <= max_hp * 0.2:
        lines.append(
            flavor.ENRAGE_LINES[0].format(boss=boss.get("target_name", "群主"))
        )
    if fight and isinstance(fight.get("board"), dict) and fight["board"]:
        total = sum(int(r.get("damage", 0)) for r in fight["board"].values())
        duration = fmt_duration(now - float(fight.get("started_at") or now))
        lines.append(
            f"⚔️ 本轮已战 {duration} · 全群输出 {total} · 参战 {len(fight['board'])} 人"
        )
    else:
        lines.append("⚔️ 本轮还未开打，/砍 抢占第一刀！")
    return "\n".join(lines)


def format_rank_text(rows: list[dict], boss_name: str) -> str:
    """/boss 排行 输出。"""
    if not rows:
        return f"还没有人砍过 {boss_name}，/砍 抢占榜首！"
    lines = [f"🏆 对 {boss_name} 的输出排行", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{medals.get(i, f'{i}.')} {row['name']} · {row['damage']} 点 · {row['hits']} 刀"
        )
    return "\n".join(lines)


def format_hall_text(rows: list[dict]) -> str:
    """/boss 名人堂 输出。"""
    if not rows:
        return "📜 还没有 Boss 倒下过。第一个弑主者会是谁？/砍 开始围剿！"
    lines = ["📜 弑主名人堂（最新在前）", ""]
    for row in rows:
        lines.append(
            f"第{row['generation']}代 · {row['boss_name']}（{row['boss_title']}）"
            f" ← {row['killer_name']} 击杀"
            f" · 全群输出 {row['total_damage']} · {fmt_duration(row['duration_s'])}"
        )
    return "\n".join(lines)


def format_me_text(report: dict | None, boss_name: str) -> str:
    """/boss 我 输出。"""
    if report is None:
        return f"你还没有对 {boss_name} 出过手，/砍 开始你的传说！"
    lines = [
        f"📋 {report.get('name', '群友')} 的战报",
        "",
        (
            f"⚔️ 累计输出：{int(report.get('total_damage', 0))} 点"
            f" · 出手 {int(report.get('hits', 0))} 刀"
        ),
        (
            f"⭐ 暴击 {int(report.get('crit', 0))} · 被闪避 {int(report.get('dodged', 0))}"
            f" · 被反击 {int(report.get('countered', 0))}"
        ),
        f"💗 心软 {int(report.get('mercy', 0))} · 神器 {int(report.get('artifact', 0))}",
        f"🗡️ 弑主 {int(report.get('kills', 0))} 次",
    ]
    titles = report.get("display_titles") or []
    lines.append(f"🏅 称号：{'、'.join(titles) if titles else '（暂无，继续肝）'}")
    return "\n".join(lines)


# ---------- T2I 图卡（use_image=true 时） ----------

_CARD_CSS = """
<style>
body { margin: 0; padding: 24px; background: #14151a; color: #e8e8f0;
       font-family: "Microsoft YaHei", "PingFang SC", sans-serif; width: 560px; }
.card { background: #1e2028; border-radius: 14px; padding: 22px 24px;
        border: 1px solid #33364a; }
.head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.name { font-size: 26px; font-weight: 700; }
.title { font-size: 15px; color: #f0b429; }
.meta { font-size: 13px; color: #9aa0b4; margin-top: 4px; }
.bar-wrap { margin: 18px 0 6px; background: #2a2d3a; border-radius: 9px;
            height: 26px; overflow: hidden; border: 1px solid #3a3e52; }
.bar { height: 100%; border-radius: 9px;
       background: linear-gradient(90deg, #e5484d, #f07a3f); }
.bar.enraged { background: linear-gradient(90deg, #ff2d55, #ff9500);
               animation: none; }
.hp-num { font-size: 15px; color: #e8e8f0; }
.tag { display: inline-block; margin-top: 10px; padding: 2px 10px;
       border-radius: 999px; background: #3a1d24; color: #ff7a90;
       font-size: 13px; }
.fight { margin-top: 14px; font-size: 14px; color: #c6cadb; }
.top { margin-top: 10px; font-size: 14px; color: #f0b429; }
</style>
"""


def build_boss_html(
    boss: dict, fight: dict | None, rows: list[dict], now: float
) -> str:
    """Boss 状态图卡 HTML（html_render 用）。"""
    hp, max_hp = int(boss["hp"]), int(boss["max_hp"])
    pct = max(0.0, min(1.0, hp / max(1, max_hp)))
    enraged = hp <= max_hp * 0.2
    name = html_escape.escape(str(boss.get("target_name", "群主")))
    title = html_escape.escape(flavor.boss_title(int(boss.get("level", 1))))

    fight_html = ""
    board = fight.get("board") if isinstance(fight, dict) else None
    if board:
        total = sum(int(r.get("damage", 0)) for r in board.values())
        duration = fmt_duration(now - float(fight.get("started_at") or now))
        fight_html = f'<div class="fight">⚔️ 本轮已战 {duration} · 全群输出 {total} · 参战 {len(board)} 人</div>'
    else:
        fight_html = '<div class="fight">⚔️ 本轮还未开打，/砍 抢占第一刀！</div>'

    top_html = ""
    if rows:
        items = "".join(
            f"<div>{i}. {html_escape.escape(r['name'])} · {r['damage']} 点</div>"
            for i, r in enumerate(rows[:3], 1)
        )
        top_html = f'<div class="top">🥇 输出榜<br>{items}</div>'

    enrage_tag = '<div class="tag">🔥 狂暴中 · 反击概率翻倍</div>' if enraged else ""
    bar_cls = "bar enraged" if enraged else "bar"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">{_CARD_CSS}</head>
<body><div class="card">
  <div class="head">
    <span class="name">⚔️ {name}</span>
    <span class="title">{title}</span>
  </div>
  <div class="meta">Lv{int(boss.get("level", 1))} · 第{int(boss.get("generation", 1))}代 · 群主养成计划</div>
  <div class="bar-wrap"><div class="{bar_cls}" style="width:{pct:.1%}"></div></div>
  <div class="hp-num">{hp} / {max_hp}（{pct:.0%}）</div>
  {enrage_tag}
  {fight_html}
  {top_html}
</div></body></html>"""
