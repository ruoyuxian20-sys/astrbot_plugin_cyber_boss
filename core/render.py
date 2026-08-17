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
    body{margin:0;padding:30px;background:#fff8f1;color:#5c4650;font-family:'Microsoft YaHei','PingFang SC',sans-serif;width:900px;position:relative}
    body:before{content:'';position:fixed;inset:0;background:radial-gradient(circle at 10% 6%,rgba(255,193,160,.55),transparent 24%),radial-gradient(circle at 90% 16%,rgba(255,170,192,.43),transparent 24%),linear-gradient(118deg,transparent 49.6%,rgba(236,163,177,.18) 50%,transparent 50.4%),linear-gradient(30deg,transparent 49.7%,rgba(121,201,204,.15) 50%,transparent 50.3%);background-size:auto,auto,150px 120px,150px 120px;pointer-events:none}
    .card{position:relative;background:rgba(255,255,255,.86);border:1px solid #fff;border-radius:28px;padding:26px;box-shadow:0 20px 50px rgba(185,126,112,.16)}
    h1{margin:0;color:#a85f70;font-size:31px}.meta{margin:8px 0 4px;color:#8f707a;font-size:15px}.equip{margin:0 0 20px;color:#9c7d80;font-size:13px}section{margin:17px 0}
    h2{margin:0;padding:9px 12px;border-radius:12px;background:linear-gradient(90deg,#fff0e6,#fff8f8);color:#b66b7b;font-size:18px}
    .shop-item{display:grid;grid-template-columns:270px 1fr;gap:3px 14px;padding:10px;border-bottom:1px dashed #efdde0}.shop-item b{color:#674852;font-size:15px}.shop-item span{color:#c07a4f;font-size:13px}.shop-item small{grid-column:1 / -1;color:#8b7178;font-size:13px}
    .foot{margin-top:20px;color:#a47c87;font-size:13px}.pig{position:absolute;right:25px;top:22px;font-size:46px;filter:drop-shadow(0 5px 6px rgba(230,132,155,.22))}
    </style>"""
    return f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\">{css}</head><body><div class=\"card\"><div class=\"pig\">🐷</div>
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
    """通用帮助/说明图卡，保留换行并转义用户数据。"""
    return f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\">{_CARD_CSS}</head>
<body class=\"view-help\"><div class=\"card panel-card\"><div class=\"pig-float\">🐷</div><div class=\"panel-kicker\">小猪养成计划</div>
<div class=\"name\">{html_escape.escape(title)}</div><div class=\"panel-rule\"></div>
<pre class=\"panel-text\">{html_escape.escape(body)}</pre></div></body></html>"""


def _dashboard_html(title: str, subtitle: str, sections: list[tuple[str, list[tuple[str, str]]]], *, variant: str, pig: str) -> str:
    """统一的网络小猪数据卡片骨架，供个人、背包、排行和名人堂复用。"""
    section_html = []
    for heading, rows in sections:
        items = "".join(
            "<div class=\"data-row\"><span>"
            + html_escape.escape(str(label))
            + "</span><strong>"
            + html_escape.escape(str(value))
            + "</strong></div>"
            for label, value in rows
        ) or '<div class="empty">暂无记录</div>'
        section_html.append(
            f"<section class=\"data-section\"><h2>{html_escape.escape(heading)}</h2>{items}</section>"
        )
    return f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\">{_CARD_CSS}</head>
<body class=\"view-{html_escape.escape(variant)}\"><div class=\"card dashboard-card\"><div class=\"pig-float\">{pig}</div><div class=\"panel-kicker\">小猪养成计划</div>
<div class=\"dashboard-title\">{html_escape.escape(title)}</div>
<div class=\"dashboard-subtitle\">{html_escape.escape(subtitle)}</div>
<div class=\"dashboard-grid\">{''.join(section_html)}</div></div></body></html>"""


def build_profile_html(report: dict, boss_name: str) -> str:
    rank = report.get("rank") or {}
    equipment = report.get("equipped") or {}
    gear_rows = []
    for slot in economy.SLOTS:
        item = economy.product(equipment.get(slot) or "")
        gear_rows.append((economy.SLOT_NAMES[slot], item["name"] if item else "未装备"))
    stats = [
        ("猎手阶位", f"{rank.get('level', 1)} 阶 · {rank.get('name', '见习猎手')}"),
        ("金币 / 印记", f"{report.get('gold', 0)} / {report.get('marks', 0)}"),
        ("累计输出", f"{report.get('total_damage', 0)} 点"),
        ("弑猪次数", f"{report.get('kills', 0)} 次"),
    ]
    combat = [
        ("当前称号", report.get("active_title_name", "未佩戴")),
        ("关键加成", economy.effect_summary(report.get("modifiers") or {})),
        ("暴击 / 神器", f"{report.get('crit', 0)} / {report.get('artifact', 0)} 次"),
        ("已武装", (economy.product(report.get("armed_consumable") or "") or {}).get("name", "无")),
    ]
    return _dashboard_html(
        f"{report.get('name', '群友')} 的战报",
        f"正在挑战：{boss_name}",
        [("成长概览", stats), ("当前配装", gear_rows), ("战斗状态", combat)], variant="profile", pig="🐷",
    )


def build_inventory_html(report: dict) -> str:
    equipment = report.get("equipped") or {}
    gear_rows = []
    for slot in economy.SLOTS:
        item = economy.product(equipment.get(slot) or "")
        gear_rows.append((economy.SLOT_NAMES[slot], item["name"] if item else "未装备"))
    inventory = report.get("inventory") or {}
    inventory_rows = [
        (f"{item_id} · {(economy.product(item_id) or {}).get('name', item_id)}", f"×{count}")
        for item_id, count in sorted(inventory.items())
    ]
    summary = [
        ("金币", str(report.get("gold", 0))),
        ("猪神印记", str(report.get("marks", 0))),
        ("已武装消耗品", (economy.product(report.get("armed_consumable") or "") or {}).get("name", "无")),
    ]
    return _dashboard_html("我的背包", "装备可自由混搭，消耗品将在下一次有效攻击时生效", [("货币与准备", summary), ("当前配装", gear_rows), ("持有物品", inventory_rows)], variant="inventory", pig="🐽")


def build_titles_html(report: dict) -> str:
    title_rows = [
        (f"{title['id']} · {title['name']}", title["description"])
        for title in report.get("title_options") or []
    ]
    return _dashboard_html(
        "称号收藏",
        f"当前佩戴：{report.get('active_title_name', '未佩戴')} · 同时只能生效一个",
        [("已解锁称号", title_rows)], variant="titles", pig="🏅",
    )


def build_rank_html(rows: list[dict], boss_name: str) -> str:
    rank_rows = [
        (f"{index}. {row.get('name', '群友')}", f"{row.get('damage', 0)} 点 · {row.get('hits', 0)} 刀")
        for index, row in enumerate(rows, 1)
    ]
    return _dashboard_html("本轮输出排行", f"目标 Boss：{boss_name}", [("伤害榜", rank_rows)], variant="rank", pig="🏁")


def build_hall_html(rows: list[dict]) -> str:
    hall_rows = [
        (
            f"第{row.get('generation', 1)}代 · {row.get('boss_name', '小猪')}",
            f"{row.get('killer_name', '群友')} 击杀 · 输出 {row.get('total_damage', 0)}",
        )
        for row in rows
    ]
    return _dashboard_html("弑猪名人堂", "最新击杀记录排在最前", [("历史战绩", hall_rows)], variant="hall", pig="🐖")


# ---------- T2I 图卡（use_image=true 时） ----------

_CARD_CSS = """
<style>
body { margin: 0; padding: 28px; background: #fff8f4; color: #5b444d;
       font-family: "Microsoft YaHei", "PingFang SC", sans-serif; width: 560px; position: relative; }
body:before, body:after { content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0; }
body:before { opacity: .9;
  background: radial-gradient(circle at 10% 8%, rgba(255,184,199,.48), transparent 28%),
  radial-gradient(circle at 92% 20%, rgba(255,210,145,.43), transparent 27%),
  linear-gradient(120deg, transparent 49.6%, rgba(236,163,177,.17) 50%, transparent 50.4%),
  linear-gradient(30deg, transparent 49.7%, rgba(121,201,204,.14) 50%, transparent 50.3%);
  background-size: auto, auto, 150px 120px, 150px 120px; }
.card { position: relative; z-index: 1; background: rgba(255,255,255,.86); border-radius: 26px; padding: 22px 24px;
        border: 1px solid rgba(255,255,255,.95); box-shadow: 0 18px 48px rgba(177,112,131,.16); }
.head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.name { font-size: 26px; font-weight: 700; color: #5a3f49; }
.title { font-size: 15px; color: #bc7182; }
.meta { font-size: 13px; color: #987985; margin-top: 4px; }
.bar-wrap { margin: 18px 0 6px; background: #ffe9eb; border-radius: 999px;
            height: 26px; overflow: hidden; border: 1px solid #ffd7de; }
.bar { height: 100%; border-radius: 9px;
       background: linear-gradient(90deg, #ff9eb3, #f8c171); }
.bar.enraged { background: linear-gradient(90deg, #f77996, #ffad58);
               animation: none; }
.hp-num { font-size: 15px; color: #684c56; }
.tag { display: inline-block; margin-top: 10px; padding: 3px 10px;
       border-radius: 999px; background: #ffe3e8; color: #cf617a;
       font-size: 13px; }
.fight { margin-top: 14px; font-size: 14px; color: #856b75; }
.top { margin-top: 10px; font-size: 14px; color: #bd7b42; }
.panel-card, .dashboard-card { border-top: 4px solid var(--accent, #f4a2b3); }
.panel-kicker { color: var(--accent-deep, #ba7483); font-size: 12px; letter-spacing: 2px; text-transform: uppercase; }
.panel-rule { height: 1px; margin: 14px 0; background: linear-gradient(90deg,var(--accent, #f3a5b5),transparent); }
.panel-text { margin: 0; white-space: pre-wrap; font: 14px/1.7 "Microsoft YaHei", "PingFang SC", sans-serif; color: #644d56; }
.dashboard-title { margin-top: 4px; color: #5a4049; font-size: 29px; font-weight: 700; }
.dashboard-subtitle { margin: 5px 0 18px; color: #917782; font-size: 14px; }
.dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.data-section { overflow: hidden; border: 1px solid var(--accent-soft, #f5dce2); border-radius: 16px; background: rgba(255,255,255,.74); }
.data-section:last-child:nth-child(odd) { grid-column: 1 / -1; }
.data-section h2 { margin: 0; padding: 9px 12px; color: var(--accent-deep, #b66d7d); font-size: 14px; background: var(--accent-wash, #fff0f3); }
.data-row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 9px 12px; border-top: 1px dashed var(--accent-soft, #f2dfe3); font-size: 13px; }
.data-row span { color: #967d86; }
.data-row strong { max-width: 66%; color: #59454d; text-align: right; font-weight: 600; }
.empty { padding: 14px 12px; color: #9d8690; font-size: 13px; }
.pig-float { position: absolute; right: 22px; top: 16px; font-size: 42px; filter: drop-shadow(0 5px 6px rgba(224,136,157,.22)); }
.view-profile { --accent:#f1a0b4; --accent-deep:#bd6f83; --accent-soft:#f5dce3; --accent-wash:#fff0f4; }
.view-inventory { --accent:#83cbd2; --accent-deep:#4b9ea8; --accent-soft:#d4eef0; --accent-wash:#ebfbfb; }
.view-titles { --accent:#bfa7e5; --accent-deep:#8466b7; --accent-soft:#e7ddf6; --accent-wash:#f5f0fc; }
.view-rank { --accent:#82c5ae; --accent-deep:#4f977e; --accent-soft:#d5ede3; --accent-wash:#effaf4; }
.view-hall { --accent:#edbc78; --accent-deep:#b97b34; --accent-soft:#f8e7c9; --accent-wash:#fff8e9; }
.view-help { --accent:#8eb9e9; --accent-deep:#5d86b5; --accent-soft:#dceafb; --accent-wash:#f0f7ff; }
.view-status { --accent:#f2a276; --accent-deep:#bd6d48; --accent-soft:#f8dfd1; --accent-wash:#fff2eb; }
/* 同一套「网络节点」语言下，各页面使用不同的内容隐喻而非仅换色。 */
.view-profile:after { background:
  radial-gradient(circle at 13% 79%, #f4a1b5 0 4px, transparent 5px),
  radial-gradient(circle at 87% 76%, #f2bd83 0 5px, transparent 6px),
  linear-gradient(151deg, transparent 47%, rgba(230,136,160,.28) 47.3%, rgba(230,136,160,.28) 47.8%, transparent 48.1%); }
.view-profile .dashboard-title { letter-spacing: .4px; }
.view-profile .data-section:first-child { background: linear-gradient(135deg, rgba(255,241,245,.96), rgba(255,255,255,.78)); }
.view-profile .data-section:first-child h2:before { content: "● "; }
.view-inventory:after { opacity: .72; background-image:
  radial-gradient(rgba(79,164,171,.26) 1.2px, transparent 1.8px),
  linear-gradient(90deg, transparent 49.5%, rgba(89,180,184,.12) 50%, transparent 50.5%),
  linear-gradient(transparent 49.5%, rgba(89,180,184,.12) 50%, transparent 50.5%);
  background-size: 20px 20px, 72px 72px, 72px 72px; background-position: 0 0, 11px 19px, 11px 19px; }
.view-inventory .data-section { border-radius: 12px 19px 12px 19px; }
.view-inventory .data-section h2:before { content: "▦ "; }
.view-titles:after { opacity: .78; background:
  radial-gradient(ellipse at 86% 16%, transparent 0 27px, rgba(154,120,204,.20) 28px 29px, transparent 30px),
  radial-gradient(ellipse at 16% 83%, transparent 0 34px, rgba(154,120,204,.17) 35px 36px, transparent 37px),
  radial-gradient(circle at 84% 16%, rgba(178,145,220,.56) 0 4px, transparent 5px),
  radial-gradient(circle at 16% 83%, rgba(178,145,220,.45) 0 5px, transparent 6px); }
.view-titles .data-section { border-radius: 22px 22px 10px 10px; }
.view-titles .data-section h2:before { content: "✦ "; }
.view-rank:after { opacity: .7; background:
  repeating-linear-gradient(153deg, transparent 0 24px, rgba(83,157,129,.13) 25px 27px, transparent 28px 51px),
  radial-gradient(circle at 88% 12%, rgba(105,190,159,.42) 0 5px, transparent 6px),
  radial-gradient(circle at 12% 86%, rgba(105,190,159,.38) 0 5px, transparent 6px); }
.view-rank .data-section { border-radius: 18px; }
.view-rank .data-section h2:before { content: "↗ "; }
.view-rank .data-row:first-of-type { background: linear-gradient(90deg, rgba(231,249,240,.95), rgba(255,255,255,.6)); }
.view-rank .data-row:first-of-type strong { color: #388064; }
.view-hall:after { opacity: .78; background:
  radial-gradient(circle at 14% 14%, rgba(234,183,102,.42) 0 5px, transparent 6px),
  radial-gradient(circle at 88% 82%, rgba(234,183,102,.38) 0 6px, transparent 7px),
  repeating-radial-gradient(ellipse at 50% 50%, transparent 0 29px, rgba(204,151,75,.10) 30px 31px, transparent 32px 57px); }
.view-hall .data-section { border: 2px solid var(--accent-soft); border-radius: 8px 22px 8px 22px; }
.view-hall .data-section h2:before { content: "♛ "; }
.view-help .data-section h2:before { content: "⌁ "; }
.view-status:after { opacity: .65; background:
  radial-gradient(circle at 90% 10%, rgba(240,150,108,.45) 0 5px, transparent 6px),
  radial-gradient(circle at 10% 88%, rgba(240,150,108,.37) 0 4px, transparent 5px),
  linear-gradient(35deg, transparent 46%, rgba(239,156,118,.16) 46.4%, rgba(239,156,118,.16) 46.9%, transparent 47.3%); }
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
<body class="view-status"><div class="card"><div class="pig-float">🐷</div>
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
