"""核心逻辑测试：不依赖 AstrBot 运行时。"""

import os
import random
import sys
import logging
from types import ModuleType

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)


def _install_astrbot_stub() -> None:
    """让入口层辅助方法也能在未安装 AstrBot 的开发环境中测试。"""
    try:
        import astrbot.api  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    class _Star:
        def __init__(self, context):
            self.context = context

    class _Filter:
        class PermissionType:
            ADMIN = "admin"

        @staticmethod
        def command(*_args, **_kwargs):
            return lambda func: func

        @staticmethod
        def command_group(*_args, **_kwargs):
            def decorate_group(func):
                func.command = lambda *_a, **_kw: (lambda child: child)
                return func

            return decorate_group

        @staticmethod
        def permission_type(*_args, **_kwargs):
            return lambda func: func

    astrbot = ModuleType("astrbot")
    api = ModuleType("astrbot.api")
    event = ModuleType("astrbot.api.event")
    star = ModuleType("astrbot.api.star")
    api.AstrBotConfig = dict
    api.logger = logging.getLogger("cyber_boss_test")
    event.AstrMessageEvent = object
    event.filter = _Filter
    star.Context = object
    star.Star = _Star
    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.star": star,
        }
    )


_install_astrbot_stub()

from cyber_boss.core import economy, engine, flavor, render, storage

# ---------- 工具 ----------


def _attack_until(kind: str, boss: dict, player: str = "张三", **kw):
    """在有限种子内找到能产生指定事件的一刀（random.Random 同种子序列稳定）。"""
    for seed in range(20000):
        result = engine.attack(random.Random(seed), dict(boss), player, **kw)
        if result.kind == kind:
            return seed, result
    raise AssertionError(f"20000 个种子内未出现事件 {kind}")


def _boss(**over) -> dict:
    boss = engine.new_boss(initial_hp=10000)
    boss.update(over)
    return boss


# ---------- 文案库完整性 ----------


def test_flavor_libraries_complete():
    assert len(flavor.HIT_QUIPS) >= 10
    assert len(flavor.CRIT_WEAPONS) >= 12
    assert len(flavor.DODGE_LINES) >= 8
    assert len(flavor.COUNTER_LINES) >= 8
    assert len(flavor.MERCY_LINES) >= 6
    assert len(flavor.ARTIFACT_LINES) >= 6
    assert len(flavor.BOSS_TITLE_LADDER) >= 8
    assert len(flavor.KILL_HEADER) >= 3
    assert len(flavor.REVIVE_LINES) >= 3
    assert len(flavor.ENRAGE_LINES) >= 2
    assert len(flavor.FIRST_BLOOD_LINES) >= 3


def test_flavor_placeholders_resolvable():
    pools = (
        flavor.HIT_QUIPS
        + flavor.DODGE_LINES
        + flavor.COUNTER_LINES
        + flavor.MERCY_LINES
        + flavor.ARTIFACT_LINES
        + flavor.KILL_HEADER
        + flavor.REVIVE_LINES
        + flavor.ENRAGE_LINES
        + flavor.FIRST_BLOOD_LINES
    )
    for template in pools:
        text = template.format(boss="老板", player="刀客")
        assert "{" not in text and "}" not in text, template
    for w in flavor.CRIT_WEAPONS:
        assert w["name"] and w["verb"]


def test_boss_title_ladder_monotonic():
    levels = [lv for lv, _ in flavor.BOSS_TITLE_LADDER]
    assert levels == sorted(levels)
    assert levels[0] == 1
    assert flavor.boss_title(1) == flavor.BOSS_TITLE_LADDER[0][1]
    assert flavor.boss_title(99) == flavor.BOSS_TITLE_LADDER[-1][1]
    # 等级递增称号只在阶梯点上变化
    assert flavor.boss_title(8) == flavor.boss_title(9)


def test_player_titles_cover_thresholds():
    for key in storage._TITLE_THRESHOLDS:
        assert key in flavor.PLAYER_TITLES, key
    assert flavor.regicide_title(3) == "弑猪者Lv3"
    assert flavor.regicide_title(0) == "弑猪者Lv1"


# ---------- 引擎 ----------


def test_new_boss_defaults():
    boss = engine.new_boss()
    assert boss["target_id"] == ""
    assert boss["target_name"] == "小猪"
    assert boss["level"] == 1 and boss["generation"] == 1
    assert boss["hp"] == boss["max_hp"] == 10000
    assert engine.new_boss(initial_hp=50)["max_hp"] == 100  # 下限保护
    named = engine.new_boss("123", " 李四 ", generation=7)
    assert named["target_id"] == "123" and named["target_name"] == "李四"
    assert named["generation"] == 7


def test_attack_deterministic_and_pure():
    boss = _boss()
    r1 = engine.attack(random.Random(42), boss, "张三")
    r2 = engine.attack(random.Random(42), boss, "张三")
    assert (r1.kind, r1.damage, r1.line) == (r2.kind, r2.damage, r2.line)
    assert boss["hp"] == 10000  # 未被修改


def test_all_event_kinds_reachable():
    kinds = {"hit", "crit", "dodge", "counter", "mercy", "artifact"}
    for kind in kinds:
        _, result = _attack_until(kind, _boss())
        assert result.kind == kind
        assert result.line


def test_attack_damage_ranges():
    _, hit = _attack_until("hit", _boss())
    assert 15 <= hit.damage <= 75
    _, crit = _attack_until("crit", _boss())
    assert 30 <= crit.damage <= 225  # 15-75 × 2-3
    _, art = _attack_until("artifact", _boss())
    assert art.damage == 500  # 500 × Lv1
    lv5 = _boss(level=5)
    _, art5 = _attack_until("artifact", lv5)
    assert art5.damage == 2500
    for kind in ("dodge", "counter"):
        _, r = _attack_until(kind, _boss())
        assert r.damage == 0
    _, mercy = _attack_until("mercy", _boss())
    assert 20 <= mercy.heal <= 80 and mercy.damage == 0


def test_mercy_heal_clamped_by_max_hp():
    boss = _boss(hp=9990)
    _, r = _attack_until("mercy", boss)
    assert r.boss["hp"] <= r.boss["max_hp"]


def test_enrage_threshold_and_counter_bias():
    assert not engine.is_enraged(_boss(hp=2001))
    assert engine.is_enraged(_boss(hp=2000))  # 20% 边界

    def counter_ratio(hp: int, max_hp: int, n: int = 3000) -> float:
        boss = _boss(hp=hp, max_hp=max_hp)
        hits = 0
        for seed in range(n):
            r = engine.attack(random.Random(seed), boss, "张三")
            if r.kind == "counter":
                hits += 1
            boss = r.boss  # 巨量血条保证全程处于同一状态，不会被砍死复活
        return hits / n

    # 满血（常态）vs 10% 血（狂暴），血条取天文数字防止中途死亡复活污染样本
    calm = counter_ratio(10**9, 10**9)
    enraged = counter_ratio(10**8, 10**9)
    assert calm < 0.12, f"常规反击率异常 {calm}"
    assert enraged > calm + 0.03, f"狂暴未提高反击率: {enraged} vs {calm}"


def test_event_weights_match_documented_percentages():
    assert sum(weight for _, weight in engine._WEIGHTS_NORMAL) == 100
    assert sum(weight for _, weight in engine._WEIGHTS_ENRAGED) == 100
    assert dict(engine._WEIGHTS_NORMAL)["hit"] == 65
    assert dict(engine._WEIGHTS_ENRAGED)["counter"] == 14


def test_equipment_modifiers_change_attack_and_counter_can_be_blocked():
    seed, _ = _attack_until("counter", _boss())
    blocked = engine.attack(
        random.Random(seed), _boss(), "张三", modifiers={"counter_block": 1.0}
    )
    assert blocked.kind == "hit"
    assert blocked.counter_blocked
    assert "格挡" in "\n".join(blocked.triggers)

    _, normal = _attack_until("hit", _boss())
    _, boosted = _attack_until("hit", _boss(), modifiers={"flat_damage": 20})
    assert boosted.damage >= normal.damage


def test_kill_revives_with_growth():
    boss = _boss(hp=10, level=3, generation=5)
    _, r = _attack_until("hit", boss)
    assert r.killed
    assert r.boss["level"] == 4
    assert r.boss["generation"] == 6
    assert r.boss["max_hp"] == round(10000 * 1.2)
    assert r.boss["hp"] == r.boss["max_hp"]
    # 非击杀路径不升级
    boss2 = _boss(hp=1000)
    _, r2 = _attack_until("hit", boss2)
    assert not r2.killed and r2.boss["level"] == 1
    assert 0 < r2.boss["hp"] < 1000
    # 成长倍率下限保护
    boss3 = _boss(hp=10, max_hp=100)
    _, r3 = _attack_until("hit", boss3, hp_growth=1.0)
    assert r3.boss["max_hp"] == round(100 * 1.05)


# ---------- 存储 ----------


def _data_with_fight() -> dict:
    data = storage.empty_group()
    data["boss"] = engine.new_boss(initial_hp=10000)
    return data


class _Res:
    """测试用 AttackResult 替身。"""

    def __init__(self, kind: str, damage: int = 0, heal: int = 0):
        self.kind = kind
        self.damage = damage
        self.heal = heal


def test_storage_roundtrip(tmp_path):
    path = str(tmp_path / "g1.json")
    data = _data_with_fight()
    storage.record_attack(data, "u1", "张三", _Res("hit", 50))
    data["boss"]["hp"] -= 50  # 血量结算由 main 负责，存储只记战报
    storage.save_group_data(path, data)
    loaded = storage.load_group_data(path)
    assert loaded["boss"]["hp"] == 9950
    assert loaded["players"]["u1"]["total_damage"] == 50


def test_load_broken_file(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    data = storage.load_group_data(path)
    assert data["boss"] is None and data["players"] == {}


def test_old_player_data_is_migrated_to_economy_schema(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"boss": null, "fight": null, "players": {"u1": {"name": "张三", "total_damage": 7}}, "hall": []}', encoding="utf-8")
    player = storage.load_group_data(str(path))["players"]["u1"]
    assert player["gold"] == player["marks"] == 0
    assert player["inventory"] == {}
    assert set(player["equipped"]) == set(economy.SLOTS)


def test_record_attack_accumulates_and_grants_titles():
    data = _data_with_fight()
    storage.record_attack(data, "u1", "张三", _Res("hit", 40), now=100.0)
    storage.record_attack(data, "u1", "张三", _Res("crit", 60), now=101.0)
    storage.record_attack(data, "u2", "李四", _Res("mercy", 0, 30), now=102.0)
    board = data["fight"]["board"]
    assert board["u1"] == {"name": "张三", "damage": 100, "hits": 2, "first_attack_at": 100.0}
    assert data["fight"]["started_at"] == 100.0  # 第一刀时间
    p1 = data["players"]["u1"]
    assert p1["total_damage"] == 100 and p1["crit"] == 1

    for i in range(4):
        storage.record_attack(data, "u2", "李四", _Res("mercy"), now=110.0 + i)
    assert "filial" in data["players"]["u2"]["titles"]  # 心软满 5 次

    for i in range(10):
        storage.record_attack(data, "u1", "张三", _Res("counter"), now=120.0 + i)
    assert "hospitalized" in data["players"]["u1"]["titles"]

    storage.record_attack(data, "u3", "王五", _Res("artifact", 500))
    assert "coder" in data["players"]["u3"]["titles"]


def test_settle_kill_flow():
    data = _data_with_fight()
    storage.record_attack(data, "u1", "张三", _Res("hit", 300), now=100.0)
    storage.record_attack(data, "u1", "张三", _Res("crit", 700), now=200.0)
    storage.record_attack(data, "u2", "李四", _Res("hit", 100), now=300.0)

    entry = storage.settle_kill(data, "u2", "李四", _Res("hit", 50), now=400.0)
    assert entry["generation"] == 1
    assert entry["boss_title"] == "新手小猪"
    assert entry["total_damage"] == 1100
    assert entry["players"] == 2
    assert entry["duration_s"] == 300.0
    assert entry["killer_kills"] == 1
    # 击杀者计数 + 主力输出给伤害最高者（张三，而非补刀的李四）
    assert data["players"]["u2"]["kills"] == 1
    assert "top_dps" in data["players"]["u1"]["titles"]
    assert "top_dps" not in data["players"]["u2"]["titles"]
    # 战局清空、名人堂最新在前
    assert data["fight"] == {"started_at": 400.0, "board": {}}
    rows = storage.hall_rows(data)
    assert rows[0]["killer_name"] == "李四"

    storage.settle_kill(data, "u2", "李四", _Res("hit", 50), now=500.0)
    assert data["players"]["u2"]["kills"] == 2
    assert storage.hall_rows(data)[0]["generation"] == 1  # 未换 Boss 代数不变


def test_kill_marks_and_tie_breaker():
    data = _data_with_fight()
    storage.record_attack(data, "u1", "甲", _Res("hit", 500), now=10.0)
    storage.record_attack(data, "u1", "甲", _Res("hit", 0), now=11.0)
    storage.record_attack(data, "u2", "乙", _Res("hit", 500), now=12.0)
    entry = storage.settle_kill(data, "u2", "乙", _Res("hit", 1), now=20.0)
    assert entry["top_id"] == "u1"  # 同伤害时攻击次数更多者获 MVP
    assert entry["rewards"]["u1"]["marks"] == 9  # 保底 1 + 贡献 4 + MVP 4
    assert entry["rewards"]["u2"]["marks"] == 8  # 保底 1 + 贡献 4 + 补刀 3

    solo = _data_with_fight()
    storage.record_attack(solo, "u3", "丙", _Res("hit", 1000), now=1.0)
    solo_entry = storage.settle_kill(solo, "u3", "丙", _Res("hit", 1), now=2.0)
    assert solo_entry["double_crown"]
    assert solo_entry["rewards"]["u3"]["marks"] == 12
    assert "double_crown" in solo["players"]["u3"]["titles"]


def test_economy_purchase_equip_arm_and_title_flow():
    data = _data_with_fight()
    player = storage.ensure_player(data, "u1", "张三", now=1.0)
    player.update({"gold": 20, "marks": 20, "total_damage": 9000, "kills": 1})
    assert not storage.buy_item(data, "u1", "张三", "MW3", 1, now=1.5)[0]
    ok, _, item = storage.buy_item(data, "u1", "张三", "GW1", 1, now=2.0)
    assert ok and item["id"] == "GW1"
    assert storage.equip_item(data, "u1", "张三", "GW1", now=3.0)[0]
    assert data["players"]["u1"]["equipped"]["weapon"] == "GW1"
    assert not storage.buy_item(data, "u1", "张三", "GW1", 1, now=4.0)[0]
    assert storage.buy_item(data, "u1", "张三", "C01", 2, now=5.0)[0]
    assert storage.arm_consumable(data, "u1", "张三", "C01", now=6.0)[0]
    assert storage.consume_armed_consumable(data["players"]["u1"])["id"] == "C01"
    assert data["players"]["u1"]["inventory"]["C01"] == 1
    assert storage.set_active_title(data, "u1", "张三", "regicide", now=7.0)[0]
    report = storage.player_report(data, "u1", "张三")
    assert report["active_title_name"] == "弑猪者Lv1"


def test_economy_limits_and_pages():
    player = {"total_damage": 0, "inventory": {}}
    rows, page, pages = economy.shop_page(player, 99)
    assert len(economy.PRODUCTS) == 56
    assert page == pages == 7 and len(rows) == 8
    for slot in economy.SLOTS:
        slot_items = [item for item in economy.PRODUCTS if item["slot"] == slot]
        assert len(slot_items) == 12
        assert sum(item["currency"] == "gold" for item in slot_items) == 6
        assert sum(item["currency"] == "marks" for item in slot_items) == 6
    modifiers = economy.combat_modifiers(
        {
            "inventory": {"GW2": 1, "MW1": 1, "C02": 1},
            "equipped": {"weapon": "MW1", "offhand": None, "armor": None, "accessory": None},
            "titles": [],
            "active_title": None,
            "armed_consumable": "C02",
            "kills": 0,
        }
    )
    assert modifiers["damage_pct"] <= 0.70


def test_economy_page_rendering_and_panel_escaping():
    report = storage.player_report(_data_with_fight(), "u1", "<刀客>")
    rows, page, pages = economy.shop_page(report, 1)
    assert "小猪商店" in render.format_shop_text(rows, page, pages, report)
    assert "我的背包" in render.format_inventory_text(report)
    assert "称号收藏" in render.format_titles_text(report)
    panel = render.build_panel_html("<商店>", "<script>")
    assert "&lt;商店&gt;" in panel and "&lt;script&gt;" in panel
    assert "view-help" in panel and "pig-float" in panel

    profile = render.build_profile_html(report, "小猪")
    inventory = render.build_inventory_html(report)
    titles = render.build_titles_html(report)
    rank_card = render.build_rank_html([{"name": "甲", "damage": 9, "hits": 2}], "小猪")
    hall_card = render.build_hall_html([{"generation": 1, "boss_name": "小猪", "killer_name": "甲", "total_damage": 9}])
    assert "view-profile" in profile and "view-inventory" in inventory
    assert "view-titles" in titles and "view-rank" in rank_card and "view-hall" in hall_card


def test_catalog_sections_and_exact_name_purchase():
    data = _data_with_fight()
    player = storage.ensure_player(data, "u1", "张三", now=1.0)
    player.update({"gold": 100, "total_damage": 3000})
    title, sections = economy.shop_sections(player, "全览")
    assert title.endswith("全目录") and len(sections) == 9
    assert sum(len(rows) for _, rows in sections) == 56
    title, affordable = economy.shop_sections(player, "可买")
    assert title.endswith("当前可购买") and affordable
    ok, _, item = storage.buy_item(data, "u1", "张三", "加粗铅笔", 1, now=2.0)
    assert ok and item["id"] == "GW4"
    catalog_html = render.build_shop_catalog_html("<商店>", sections, player)
    assert "&lt;商店&gt;" in catalog_html and "磨刀石" in catalog_html


def test_help_topics_cover_public_command_groups():
    from cyber_boss import main

    assert set(main._HELP_TOPICS) == {"战斗", "商店", "装备", "称号"}
    assert "/boss 商店 可买" in main._HELP_TOPICS["商店"]
    assert "/砍猪" in main._HELP_TEXT


def test_ranking_sorted():
    data = _data_with_fight()
    for uid, name, dmg in (("u1", "甲", 100), ("u2", "乙", 300), ("u3", "丙", 200)):
        storage.record_attack(data, uid, name, _Res("hit", dmg))
    rows = storage.ranking(data, 2)
    assert [r["name"] for r in rows] == ["乙", "丙"]
    assert rows[0]["damage"] == 300


def test_player_report_titles():
    data = _data_with_fight()
    storage.record_attack(data, "u1", "张三", _Res("hit", 10))
    report = storage.player_report(data, "u1")
    assert report["display_titles"] == []  # 无击杀无成就
    storage.settle_kill(data, "u1", "张三", _Res("hit", 10))
    report = storage.player_report(data, "u1")
    assert report["display_titles"] == ["弑猪者Lv1", "主力输出", "双冠斩首"]
    assert storage.player_report(data, "nobody")["gold"] == 0


# ---------- 渲染 ----------


def test_text_bar_and_duration():
    assert render.text_bar(5000, 10000) == "█████░░░░░ 50%"
    assert render.text_bar(0, 10000).endswith("0%")
    assert render.text_bar(12000, 10000) == "██████████ 100%"  # 溢出钳制
    assert render.fmt_duration(59) == "59 秒"
    assert "分" in render.fmt_duration(61)
    assert "小时" in render.fmt_duration(3600 * 5)
    assert "天" in render.fmt_duration(3600 * 25)


def test_format_outputs_shape():
    boss = _boss(hp=8000)
    r = engine.attack(random.Random(7), boss, "张三")
    text = render.format_attack_text(r, r.boss)
    assert boss["target_name"] in text

    status = render.format_status_text(_boss(hp=1500), None, [], now=1000.0)
    assert "狂暴" in status
    fight = {
        "started_at": 0.0,
        "board": {"u1": {"name": "张三", "damage": 3, "hits": 1}},
    }
    assert "全群输出 3" in render.format_status_text(_boss(), fight, [], now=100.0)

    rank = render.format_rank_text([{"name": "甲", "damage": 9, "hits": 2}], "小猪")
    assert "甲" in rank and "还没" in render.format_rank_text([], "小猪")

    hall = storage.hall_rows({"hall": []})
    assert render.format_hall_text(hall).startswith("📜")

    me = render.format_me_text(None, "小猪")
    assert "/砍猪" in me


def test_format_kill_text():
    data = _data_with_fight()
    storage.record_attack(data, "u1", "张三", _Res("hit", 5000), now=0.0)
    storage.record_attack(data, "u2", "李四", _Res("hit", 5000), now=10.0)
    entry = storage.settle_kill(data, "u2", "李四", _Res("hit", 1), now=20.0)
    assert entry["top_name"] == "张三" and entry["top_damage"] == 5000
    boss_after = engine.new_boss(initial_hp=12000)
    boss_after.update({"level": 2, "generation": 2, "target_name": "小猪"})
    text = render.format_kill_text(
        _Res("hit", 1), boss_after, "李四", entry, random.Random(1)
    )
    assert "李四" in text and "弑猪者Lv1" in text
    assert "张三" in text and "主力输出" in text
    assert "Lv2" in text and "已读不回猪仔" in text


def test_build_boss_html():
    fight = {
        "started_at": 0.0,
        "board": {"u1": {"name": "张三", "damage": 3, "hits": 1}},
    }
    html = render.build_boss_html(
        _boss(hp=1500), fight, [{"name": "张三", "damage": 3}], 100.0
    )
    assert "小猪" in html and "新手小猪" in html and "狂暴" in html and "view-status" in html
    escaped = render.build_boss_html(_boss(target_name="<script>"), None, [], 0.0)
    assert "<script>" not in escaped and "&lt;script&gt;" in escaped


# ---------- 主入口可导入 ----------


def test_main_importable():
    from cyber_boss.main import CyberBoss

    assert CyberBoss is not None


def test_at_target_duck_typing():
    """/boss 养 的 @ 解析：只认带 qq 属性的消息段，AtAll 跳过。"""
    from cyber_boss.main import CyberBoss

    class _Seg:
        def __init__(self, qq, name=""):
            self.qq, self.name = qq, name

    class _Msg:
        def __init__(self, segs):
            self.message = segs

    class _Ev:
        def __init__(self, segs):
            self.message_obj = _Msg(segs)

    bot = CyberBoss(None, {})
    assert bot._at_target(_Ev([_Seg("2000", "赵六")])) == ("2000", "赵六")
    assert bot._at_target(_Ev([_Seg("2000")])) == ("2000", "群友2000")
    assert bot._at_target(_Ev([_Seg("all", "所有人")])) == ("", "")
    assert bot._at_target(_Ev(["一段纯文本"])) == ("", "")
    assert bot._at_target(_Ev([])) == ("", "")

    class _Broken:
        @property
        def message(self):
            raise RuntimeError("boom")

    class _BrokenMsg:
        message_obj = _Broken()

    assert bot._at_target(_BrokenMsg()) == ("", "")


def test_group_path_is_safe_and_keeps_normal_ids_readable(tmp_path):
    from cyber_boss.main import CyberBoss

    bot = CyberBoss(None, {})
    bot._data_dir = lambda: str(tmp_path)
    assert bot._group_path("12345").endswith("12345.json")
    unsafe = bot._group_path("../outside")
    assert os.path.dirname(unsafe) == str(tmp_path)
    assert os.path.basename(unsafe).startswith("key_")
    assert os.path.basename(unsafe).endswith(".json")


def test_flush_keeps_failed_groups_dirty_for_retry(tmp_path, monkeypatch):
    from cyber_boss.main import CyberBoss

    bot = CyberBoss(None, {})
    bot._data_dir = lambda: str(tmp_path)
    bot._groups = {"ok": {"state": "ok"}, "bad": {"state": "bad"}}
    bot._dirty = {"ok", "bad"}
    bot._ops_since_save = 1
    saved = []

    def save_once(path, data):
        if data["state"] == "bad":
            raise OSError("disk full")
        saved.append(path)

    monkeypatch.setattr(storage, "save_group_data", save_once)
    bot._flush(force=True)
    assert len(saved) == 1
    assert bot._dirty == {"bad"}
    assert bot._ops_since_save == 20

    monkeypatch.setattr(storage, "save_group_data", lambda path, data: saved.append(path))
    bot._flush(force=True)
    assert len(saved) == 2
    assert not bot._dirty
