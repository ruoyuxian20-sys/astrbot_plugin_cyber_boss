"""输出格式化：文本血条、战报文案、可选 T2I 图卡 HTML。"""

from __future__ import annotations

import html as html_escape
import random

from . import economy, flavor

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
        f"⚔️ {boss.get('target_name', '小猪')} · {name}"
        f" · Lv{int(boss.get('level', 1))} · 第{int(boss.get('generation', 1))}代"
    )


def format_attack_text(result, boss: dict) -> str:
    """一次 /砍猪 的纯文本输出（不含击杀播报，那由 format_kill_text 负责）。"""
    name = boss.get("target_name", "小猪")
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
    lines.extend(getattr(result, "triggers", []))
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
    old_name = entry.get("boss_name", "小猪")
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
    if entry.get("double_crown"):
        lines.append("👑 双冠斩首：MVP 与最后一刀由同一人拿下！")
    rewards = entry.get("rewards") or {}
    if rewards:
        reward_rows = sorted(rewards.values(), key=lambda row: (-row["marks"], -row["damage"]))
        reward_lines = " · ".join(
            f"{row['name']} +{row['marks']}印记"
            for row in reward_rows[:10]
        )
        if len(reward_rows) > 10:
            reward_lines += f" · 等 {len(reward_rows)} 人"
        lines.append(f"🪙 击杀印记：{reward_lines}")
    new_title = flavor.boss_title(int(boss_after.get("level", 2)))
    new_name = boss_after.get("target_name", "小猪")
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
            flavor.ENRAGE_LINES[0].format(boss=boss.get("target_name", "小猪"))
        )
    if fight and isinstance(fight.get("board"), dict) and fight["board"]:
        total = sum(int(r.get("damage", 0)) for r in fight["board"].values())
        duration = fmt_duration(now - float(fight.get("started_at") or now))
        lines.append(
            f"⚔️ 本轮已战 {duration} · 全群输出 {total} · 参战 {len(fight['board'])} 人"
        )
    else:
        lines.append("⚔️ 本轮还未开打，/砍猪 抢占第一刀！")
    return "\n".join(lines)


def format_rank_text(rows: list[dict], boss_name: str) -> str:
    """/boss 排行 输出。"""
    if not rows:
        return f"还没有人砍过 {boss_name}，/砍猪 抢占榜首！"
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
        return "📜 还没有 Boss 倒下过。第一个弑猪者会是谁？/砍猪 开始围剿！"
    lines = ["📜 弑猪名人堂（最新在前）", ""]
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
        return f"你还没有对 {boss_name} 出过手，/砍猪 开始你的传说！"
    rank = report.get("rank") or {"level": 1, "name": "见习猎手", "next_damage": 2000}
    lines = [
        f"📋 {report.get('name', '群友')} 的战报",
        "",
        f"🎖️ 猎手 {rank['level']} 阶 · {rank['name']}",
        f"💰 金币 {int(report.get('gold', 0))} · 🪙 猪神印记 {int(report.get('marks', 0))}",
        (
            f"⚔️ 累计输出：{int(report.get('total_damage', 0))} 点"
            f" · 出手 {int(report.get('hits', 0))} 刀"
        ),
        (
            f"⭐ 暴击 {int(report.get('crit', 0))} · 被闪避 {int(report.get('dodged', 0))}"
            f" · 被反击 {int(report.get('countered', 0))}"
        ),
        f"💗 心软 {int(report.get('mercy', 0))} · 神器 {int(report.get('artifact', 0))}",
        f"🗡️ 弑猪 {int(report.get('kills', 0))} 次",
    ]
    titles = report.get("display_titles") or []
    lines.append(f"🏅 当前称号：{report.get('active_title_name', '未佩戴')}")
    lines.append(f"✨ 加成：{economy.effect_summary(report.get('modifiers') or {})}")
    if rank.get("next_damage") is not None:
        lines.append(f"📈 距下一阶还差 {max(0, rank['next_damage'] - int(report.get('total_damage', 0)))} 输出")
    lines.append("📦 /boss 背包 查看配装 · /boss 商店 购买道具")
    return "\n".join(lines)


def format_shop_text(rows: list[dict], page: int, pages: int, report: dict) -> str:
    rank = report.get("rank") or {"level": 1}
    lines = [
        f"🛒 小猪商店 · 第 {page}/{pages} 页",
        f"💰 金币 {report.get('gold', 0)} · 🪙 印记 {report.get('marks', 0)} · 猎手 {rank['level']} 阶",
        "",
    ]
    for item in rows:
        currency = "金币" if item["currency"] == "gold" else "印记"
        slot = f" · {economy.SLOT_NAMES[item['slot']]}" if item.get("slot") else " · 消耗品"
        locked = " 🔒" if not item["available"] else ""
        owned = f"（持有 {item['owned']}）" if item["owned"] else ""
        lines.append(f"{item['id']} {item['name']}{slot}{locked}")
        lines.append(f"  {item['price']} {currency} · 需{item['rank']}阶 {owned}")
        lines.append(f"  {item['description']}")
    lines.append("\n/boss 购买 <商品ID> [数量] · /boss 商店 <页码>")
    return "\n".join(lines)


def format_shop_catalog_text(title: str, sections: list[tuple[str, list[dict]]], report: dict) -> str:
    """完整目录的紧凑文本回退，一次输出全部区块。"""
    rank = report.get("rank") or {"level": 1}
    lines = [
        f"🛒 {title}",
        f"💰 金币 {report.get('gold', 0)} · 🪙 印记 {report.get('marks', 0)} · 猎手 {rank['level']} 阶",
    ]
    for section, rows in sections:
        lines.extend(["", f"【{section}】"])
        if not rows:
            lines.append("（暂无符合条件的商品）")
            continue
        for item in rows:
            currency = "金币" if item["currency"] == "gold" else "印记"
            state = "✅" if item["available"] else "🔒"
            owned = f" · 持有{item['owned']}" if item["owned"] else ""
            lines.append(
                f"{state} {item['id']} {item['name']} · {item['price']}{currency} · {item['rank']}阶{owned}\n  {item['description']}"
            )
    lines.append("\n/boss 购买 <商品ID|完整名称> [数量] · /boss 商店 可买")
    return "\n".join(lines)


def build_shop_catalog_html(title: str, sections: list[tuple[str, list[dict]]], report: dict) -> str:
    """完整商店长图：一个区块一张紧凑表，适合一次浏览全部商品。"""
    rank = report.get("rank") or {"level": 1, "name": "见习猎手"}
    equipped = report.get("equipped") or {}
    equipped_text = " · ".join(
        f"{economy.SLOT_NAMES[slot]}：{(economy.product(equipped.get(slot) or '') or {}).get('name', '空')}"
        for slot in economy.SLOTS
    )
    section_html = []
    for section, rows in sections:
        items = []
        for item in rows:
            currency = "金币" if item["currency"] == "gold" else "印记"
            state = "可购" if item["available"] else "未解锁"
            owned = f" · 持有 {item['owned']}" if item["owned"] else ""
            items.append(
                "<div class=\"shop-item\">"
                f"<b>{html_escape.escape(item['id'])} · {html_escape.escape(item['name'])}</b>"
                f"<span>{item['price']} {currency} · {item['rank']}阶 · {state}{owned}</span>"
                f"<small>{html_escape.escape(item['description'])}</small>"
                "</div>"
            )
        section_html.append(
            f"<section><h2>{html_escape.escape(section)}</h2>{''.join(items) or '<p>暂无符合条件的商品</p>'}</section>"
        )
    css = """
    <style>
    body{margin:0;padding:28px;background:#121722;color:#edf2ff;font-family:'Microsoft YaHei','PingFang SC',sans-serif;width:860px}
    .card{background:#1b2333;border:1px solid #31405a;border-radius:16px;padding:24px}
    h1{margin:0;color:#ffd56a;font-size:30px} .meta{margin:8px 0 4px;color:#c4d0e8;font-size:15px}
    .equip{margin:0 0 20px;color:#98a8c8;font-size:13px} section{margin:18px 0}
    h2{margin:0;padding:8px 12px;background:#27344b;border-radius:8px;color:#9dd6ff;font-size:18px}
    .shop-item{display:grid;grid-template-columns:260px 1fr;gap:3px 14px;padding:9px 10px;border-bottom:1px solid #2d394e}
    .shop-item b{color:#f4f7ff;font-size:15px}.shop-item span{color:#f7c85e;font-size:13px}.shop-item small{grid-column:1 / -1;color:#bdc9dc;font-size:13px}
    .foot{margin-top:20px;color:#8fa3c8;font-size:13px}
    </style>"""
    return f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\">{css}</head><body><div class=\"card\">
    <h1>{html_escape.escape(title)}</h1>
    <div class=\"meta\">💰 {int(report.get('gold', 0))} 金币 · 🪙 {int(report.get('marks', 0))} 印记 · 猎手 {rank['level']} 阶 · {html_escape.escape(rank.get('name', ''))}</div>
    <div class=\"equip\">当前配装：{html_escape.escape(equipped_text)}</div>
    {''.join(section_html)}
    <div class=\"foot\">/boss 购买 &lt;商品ID|完整名称&gt; [数量] · /boss 商店 可买</div>
    </div></body></html>"""


def format_inventory_text(report: dict) -> str:
    inventory = report.get("inventory") or {}
    equipped = report.get("equipped") or {}
    lines = ["🎒 我的背包", f"💰 {report.get('gold', 0)} 金币 · 🪙 {report.get('marks', 0)} 印记", "", "🧩 当前配装"]
    for slot in economy.SLOTS:
        item = economy.product(equipped.get(slot) or "")
        lines.append(f"{economy.SLOT_NAMES[slot]}：{item['name'] if item else '（空）'}")
    armed = economy.product(report.get("armed_consumable") or "")
    lines.append(f"\n🎯 已武装：{armed['name'] if armed else '（无）'}")
    lines.append("\n📦 持有物品")
    if not inventory:
        lines.append("（空）")
    else:
        for item_id, count in sorted(inventory.items()):
            item = economy.product(item_id)
            lines.append(f"{item_id} {item['name'] if item else item_id} ×{count}")
    lines.append("\n/boss 装备 <ID> · /boss 使用 <ID> · /boss 卸下 <栏位>")
    return "\n".join(lines)


def format_titles_text(report: dict) -> str:
    titles = report.get("title_options") or []
    lines = ["🏅 称号收藏", f"当前佩戴：{report.get('active_title_name', '未佩戴')}", ""]
    if not titles:
        lines.append("尚未解锁称号；参与击杀、冲击 MVP 或触发事件来获得。")
    for title in titles:
        lines.append(f"{title['id']} · {title['name']}：{title['description']}")
    lines.append("\n/boss 佩戴称号 <称号ID>（同时只能生效一个）")
    return "\n".join(lines)


def build_panel_html(title: str, body: str) -> str:
    """通用图卡页面，保留换行并转义用户数据。"""
    return f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\">{_CARD_CSS}</head>
<body><div class=\"card\"><div class=\"name\">{html_escape.escape(title)}</div>
<pre style=\"white-space:pre-wrap;font:14px Microsoft YaHei;color:#e8e8f0;line-height:1.6\">{html_escape.escape(body)}</pre>
</div></body></html>"""


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
    name = html_escape.escape(str(boss.get("target_name", "小猪")))
    title = html_escape.escape(flavor.boss_title(int(boss.get("level", 1))))

    fight_html = ""
    board = fight.get("board") if isinstance(fight, dict) else None
    if board:
        total = sum(int(r.get("damage", 0)) for r in board.values())
        duration = fmt_duration(now - float(fight.get("started_at") or now))
        fight_html = f'<div class="fight">⚔️ 本轮已战 {duration} · 全群输出 {total} · 参战 {len(board)} 人</div>'
    else:
        fight_html = '<div class="fight">⚔️ 本轮还未开打，/砍猪 抢占第一刀！</div>'

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
  <div class="meta">Lv{int(boss.get("level", 1))} · 第{int(boss.get("generation", 1))}代 · 小猪养成计划</div>
  <div class="bar-wrap"><div class="{bar_cls}" style="width:{pct:.1%}"></div></div>
  <div class="hp-num">{hp} / {max_hp}（{pct:.0%}）</div>
  {enrage_tag}
  {fight_html}
  {top_html}
</div></body></html>"""
