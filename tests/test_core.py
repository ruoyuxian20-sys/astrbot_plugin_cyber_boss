"""核心逻辑测试：不依赖 AstrBot 运行时。"""

import os
import random
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from cyber_boss.core import engine, flavor, render, storage

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


def test_record_attack_accumulates_and_grants_titles():
    data = _data_with_fight()
    storage.record_attack(data, "u1", "张三", _Res("hit", 40), now=100.0)
    storage.record_attack(data, "u1", "张三", _Res("crit", 60), now=101.0)
    storage.record_attack(data, "u2", "李四", _Res("mercy", 0, 30), now=102.0)
    board = data["fight"]["board"]
    assert board["u1"] == {"name": "张三", "damage": 100, "hits": 2}
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
    assert report["display_titles"] == ["弑猪者Lv1", "主力输出"]
    assert storage.player_report(data, "nobody") is None


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
    assert "/砍" in me


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
    assert "小猪" in html and "新手小猪" in html and "狂暴" in html
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
