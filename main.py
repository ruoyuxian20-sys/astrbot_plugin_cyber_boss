"""小猪养成计划插件：小猪是全群共享 Boss，随手一刀，越砍越强。"""

from __future__ import annotations

import os
import random
import re
import time
from hashlib import sha256

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core import economy, engine, flavor, storage
from .core.render import (
    build_boss_html,
    build_hall_html,
    build_inventory_html,
    build_panel_html,
    build_profile_html,
    build_rank_html,
    build_shop_catalog_html,
    build_titles_html,
    format_attack_text,
    format_hall_text,
    format_inventory_text,
    format_kill_text,
    format_me_text,
    format_rank_text,
    format_shop_catalog_text,
    format_status_text,
    format_titles_text,
)

_HELP_TEXT = """⚔️ 小猪养成计划 · 指令总览

/砍猪
    攻击 Boss，掉落金币；已武装消耗品会在本次结算使用
/boss 状态
    Boss 血条、等级、狂暴和本轮战况
/boss 养 @某人
    管理员换养新 Boss；不会清除玩家资产
/boss 排行
    本轮输出排行
/boss 名人堂
    历代击杀记录
/boss 我
    个人战报、货币、猎手阶位与当前加成
/boss 商店 [全览|可买|武器|副手|护具|饰品|消耗品|金币|印记]
    一张长图浏览完整商品目录；可按条件筛选
/boss 购买 <商品ID|完整名称> [数量]
    购买装备或消耗品
/boss 背包
    查看物品、四栏配装和已武装消耗品
/boss 装备 <商品ID> /boss 卸下 <武器|副手|护具|饰品>
    管理四栏装备
/boss 使用 <消耗品ID>
    武装一个消耗品，作用于下一次实际结算的 /砍猪
/boss 称号
    查看解锁称号；/boss 佩戴称号 <称号ID> 选择一个生效
/boss 帮助 [战斗|商店|装备|称号]
    查看本总览或主题页

提示：首次游玩建议依次使用 /砍猪 → /boss 商店 → /boss 背包。"""

_HELP_TOPICS = {
    "战斗": """⚔️ 战斗指南

/砍猪
    发起一次攻击。普通、暴击、闪避、反击、心软、神器都会影响本刀结果。
    每次实际结算都会掉落金币；冷却和住院拦截时不会消耗已武装道具。

/boss 状态 /boss 排行 /boss 名人堂
    分别查看血条战况、本轮输出和历代击杀。

Boss 血量 ≤20% 进入狂暴：反击概率翻倍，但也是斩杀装备发挥的时机。""",
    "商店": """🛒 商店指南

/boss 商店
    一张长图查看全部商品，不需要翻页。
/boss 商店 可买
    只显示当前阶位已解锁且余额足够的商品。
/boss 商店 武器|副手|护具|饰品|消耗品|金币|印记
    按类别筛选。
/boss 购买 <商品ID|完整名称> [数量]
    可直接用 ID 或完整名称购买；装备不能重复购买，消耗品最多持有 99 个。

金币用于常规装备与消耗品；猪神印记来自击杀结算，用于高阶装备。""",
    "装备": """🧩 装备指南

共有武器、副手、护具、饰品四栏，每栏同时只能装备一件，但可以完全自由混搭。
/boss 背包
    查看库存、货币和当前配装。
/boss 装备 <商品ID>
    装备背包中已有的装备；同栏新装备会替换旧装备。
/boss 卸下 <武器|副手|护具|饰品>
    卸下对应栏位。

装备围绕伤害、暴击、连击、神器、闪避、反击、心软、狂暴和资源收益发挥作用；没有套装限制。""",
    "称号": """🏅 称号指南

/boss 称号
    查看已经解锁的称号与效果。
/boss 佩戴称号 <称号ID>
    选择一个称号生效；称号永久收藏，但同一时间只能佩戴一个。

弑猪者来自击杀，主力输出来自 MVP，双冠斩首来自同轮 MVP 加补刀；小猪孝子、住院常客、代码术士来自特殊事件成就。""",
}
_HELP_TOPIC_ALIASES = {"fight": "战斗", "shop": "商店", "gear": "装备", "equipment": "装备", "title": "称号", "titles": "称号"}

_GROUP_WORDS = {"boss", "小猪", "养成"}
_SUB_WORDS = {
    "help",
    "帮助",
    "菜单",
    "status",
    "状态",
    "血条",
    "查看",
    "raise",
    "养",
    "换",
    "换养",
    "rank",
    "排行",
    "排行榜",
    "伤害榜",
    "输出",
    "hall",
    "名人堂",
    "历史",
    "me",
    "我",
    "战报",
    "我的",
}
_SAFE_GROUP_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")


class CyberBoss(Star):
    """小猪养成计划：全群共斗养成小游戏，不调用 LLM。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._groups: dict[str, dict] = {}
        self._dirty: set[str] = set()
        self._last_save = 0.0
        self._ops_since_save = 0
        self._rng = random.Random()
        # 住院（被反击）与防刷冷却：内存态，重启即清零，无伤大雅
        self._hospital: dict[str, float] = {}
        self._cooldown: dict[str, float] = {}

    # ---------- 工具 ----------

    def _cfg(self, key: str, default):
        try:
            return self.config.get(key, default)
        except Exception:
            return default

    def _data_dir(self) -> str:
        try:
            base = getattr(self.context, "data_dir", None) or "data"
        except Exception:
            base = "data"
        return os.path.join(base, "plugins", "cyber_boss")

    def _sender_id(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id() or "")
        except Exception:
            return ""

    def _sender_name(self, event: AstrMessageEvent) -> str:
        try:
            return (event.get_sender_name() or "").strip()
        except Exception:
            return ""

    def _group_key(self, event: AstrMessageEvent) -> str:
        try:
            gid = event.get_group_id() or ""
        except Exception:
            gid = ""
        if gid:
            return str(gid)
        return "dm_" + (self._sender_id(event) or "unknown")

    def _player_key(self, event: AstrMessageEvent) -> str:
        return f"{self._group_key(event)}:{self._sender_id(event)}"

    def _hospital_seconds(self) -> int:
        try:
            return max(5, int(self._cfg("hospital_seconds", 60)))
        except Exception:
            return 60

    def _cooldown_seconds(self) -> float:
        try:
            return max(0.0, float(self._cfg("attack_cooldown_seconds", 3)))
        except Exception:
            return 3.0

    def _hp_growth(self) -> float:
        try:
            return max(1.05, float(self._cfg("hp_growth", 1.2)))
        except Exception:
            return 1.2

    def _initial_hp(self) -> int:
        try:
            return max(100, int(self._cfg("initial_hp", 10000)))
        except Exception:
            return 10000

    def _ranking_size(self) -> int:
        try:
            return max(1, int(self._cfg("ranking_size", 10)))
        except Exception:
            return 10

    def _hospital_seconds_with_modifiers(self, modifiers: dict[str, float]) -> int:
        reduction = min(0.60, max(0.0, float(modifiers.get("hospital_reduction", 0.0))))
        return max(5, round(self._hospital_seconds() * (1 - reduction)))

    async def _panel_result(self, event: AstrMessageEvent, title: str, body: str, card_html: str | None = None):
        """商店、背包与个人页的图文回退输出。"""
        if self._cfg("use_image", False):
            try:
                url = await self.html_render(card_html or build_panel_html(title, body), {})
                return event.image_result(url)
            except Exception as e:
                logger.warning(f"cyber_boss {title} 图片渲染失败，回退纯文本: {e}")
        return event.plain_result(body)

    def _at_target(self, event: AstrMessageEvent) -> tuple[str, str]:
        """从消息段里解析第一个被 @ 的人（防御式，兼容各平台组件实现）。"""
        try:
            segments = event.message_obj.message or []
        except Exception:
            return "", ""
        for seg in segments:
            try:
                # 鸭子判定：At 组件带 qq 属性；AtAll 的 qq == "all" 跳过
                qq = str(getattr(seg, "qq", "") or "")
                if not qq or qq == "all":
                    continue
                name = (getattr(seg, "name", "") or "").strip()
                return qq, name or f"群友{qq}"
            except Exception:
                continue
        return "", ""

    # ---------- 群数据 ----------

    def _group_data(self, key: str) -> dict:
        data = self._groups.get(key)
        if data is None:
            data = storage.load_group_data(self._group_path(key))
            self._groups[key] = data
        return data

    def _group_path(self, key: str) -> str:
        """返回群数据路径，避免外部平台 ID 被解释成文件路径。"""
        if _SAFE_GROUP_KEY_RE.fullmatch(key):
            filename = key
        else:
            filename = f"key_{sha256(key.encode('utf-8')).hexdigest()}"
        return os.path.join(self._data_dir(), f"{filename}.json")

    def _boss(self, data: dict) -> dict:
        """取当前 Boss；没有则生成第 1 代虚拟小猪。"""
        boss = data.get("boss")
        if not isinstance(boss, dict) or not boss:
            boss = engine.new_boss(initial_hp=self._initial_hp())
            data["boss"] = boss
        return boss

    def _touch(self, key: str) -> None:
        self._dirty.add(key)
        self._ops_since_save += 1
        self._flush()

    def _flush(self, force: bool = False) -> None:
        if not self._dirty:
            return
        now = time.time()
        if not force and now - self._last_save < 30 and self._ops_since_save < 20:
            return
        for key in list(self._dirty):
            try:
                storage.save_group_data(
                    self._group_path(key),
                    self._groups.get(key, storage.empty_group()),
                )
            except Exception as e:
                logger.warning(f"cyber_boss 保存群数据失败 {key}: {e}")
            else:
                self._dirty.discard(key)
        if self._dirty:
            # 保留失败项，并让下一次状态变更立即触发重试。
            self._ops_since_save = 20
            return
        self._last_save = now
        self._ops_since_save = 0

    def _prune_memory(self, now: float) -> None:
        """清理过期的住院/冷却记录，防内存缓慢增长。"""
        if len(self._hospital) > 512:
            for k in [k for k, until in self._hospital.items() if now > until]:
                self._hospital.pop(k, None)
        if len(self._cooldown) > 512:
            for k in [k for k, ts in self._cooldown.items() if now - ts > 60]:
                self._cooldown.pop(k, None)

    # ---------- 核心动作：/砍猪 ----------

    @filter.command("砍猪")
    async def slash_cmd(self, event: AstrMessageEvent):
        """/砍猪 — 攻击共享 Boss，结算随机事件、装备效果、消耗品和金币掉落。"""
        uid = self._sender_id(event) or "unknown"
        name = self._sender_name(event) or "群友"
        key = self._group_key(event)
        pkey = f"{key}:{uid}"
        now = time.time()
        self._prune_memory(now)

        if now - self._cooldown.get(pkey, 0.0) < self._cooldown_seconds():
            return  # 冷却中静默忽略，避免刷屏
        left = self._hospital.get(pkey, 0.0) - now
        if left > 0:
            yield event.plain_result(
                f"🩹 你还在住院观察中，剩 {int(left) + 1} 秒。被反击就是这么疼。"
            )
            return

        data = self._group_data(key)
        boss = self._boss(data)
        first_blood = not ((data.get("fight") or {}).get("board") or {})
        prev_titles = set(
            ((data.get("players") or {}).get(uid) or {}).get("titles", [])
        )

        player_state = storage.ensure_player(data, uid, name, now)
        modifiers = economy.combat_modifiers(player_state)
        result = engine.attack(
            self._rng,
            boss,
            name,
            hp_growth=self._hp_growth(),
            modifiers=modifiers,
        )
        gold = economy.gold_drop(result.damage, result.kind, modifiers)
        player = storage.record_attack(data, uid, name, result, gold=gold, now=now)
        consumed = storage.consume_armed_consumable(player_state)
        if result.kind == "counter":
            self._hospital[pkey] = now + self._hospital_seconds_with_modifiers(modifiers)
        self._cooldown[pkey] = now

        if result.killed:
            entry = storage.settle_kill(data, uid, name, result, now=now)
            data["boss"] = result.boss
            self._touch(key)
            self._flush(force=True)
            yield event.plain_result(
                format_kill_text(result, result.boss, name, entry, rng=self._rng)
                + f"\n💰 本刀掉落 {gold} 金币"
                + (f" · 消耗了 {consumed['name']}" if consumed else "")
            )
            return

        data["boss"] = result.boss
        self._touch(key)

        body_parts = []
        if first_blood and result.damage > 0:
            body_parts.append(
                self._rng.choice(flavor.FIRST_BLOOD_LINES).format(
                    player=name, boss=engine.boss_display_name(boss)
                )
            )
        body_parts.append(format_attack_text(result, result.boss))
        body_parts.append(f"💰 掉落 {gold} 金币")
        if consumed:
            body_parts.append(f"🎯 已消耗 {consumed['name']}")
        if result.kind == "counter":
            body_parts.append(f"⏳ 住院 {self._hospital_seconds_with_modifiers(modifiers)} 秒后再战")
        gained = [
            flavor.PLAYER_TITLES.get(t, t)
            for t in player.get("titles", [])
            if t not in prev_titles
        ]
        if gained:
            body_parts.append(f"🏅 解锁称号：「{'」、「'.join(gained)}」")
        yield event.plain_result("\n".join(body_parts))

    # ---------- 命令组 ----------

    @filter.command_group("boss", alias={"小猪", "养成"})
    def boss():
        """/boss — 小猪养成计划命令组；使用 /boss 帮助 查看完整总览与主题指南。"""

    @boss.command("help", alias={"帮助", "菜单"})
    async def help_cmd(self, event: AstrMessageEvent, topic: str = ""):
        """/boss 帮助 [战斗|商店|装备|称号] — 查看总览或按主题阅读完整玩法说明。"""
        key = str(topic or "").strip()
        key = _HELP_TOPIC_ALIASES.get(key.lower(), key)
        if not key:
            body = _HELP_TEXT
            title = "小猪养成帮助"
        elif key in _HELP_TOPICS:
            body = _HELP_TOPICS[key]
            title = f"小猪养成 · {key}"
        else:
            body = _HELP_TEXT + "\n\n可选主题：战斗、商店、装备、称号。"
            title = "小猪养成帮助"
        yield await self._panel_result(event, title, body)

    @boss.command("status", alias={"状态", "血条", "查看"})
    async def status_cmd(self, event: AstrMessageEvent):
        """/boss 状态 — 查看 Boss 血条、等级、狂暴标记和本轮战况。"""
        key = self._group_key(event)
        data = self._group_data(key)
        boss_data = self._boss(data)
        rows = storage.ranking(data, 3)
        if self._cfg("use_image", False):
            try:
                url = await self.html_render(
                    build_boss_html(boss_data, data.get("fight"), rows, time.time()),
                    {},
                )
                yield event.image_result(url)
                return
            except Exception as e:
                logger.warning(f"cyber_boss 图片渲染失败，回退纯文本: {e}")
        yield event.plain_result(
            format_status_text(boss_data, data.get("fight"), rows, time.time())
        )

    @boss.command("raise", alias={"养", "换", "换养"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def raise_cmd(self, event: AstrMessageEvent):
        """/boss 养 @某人 — 管理员换养新 Boss；重置当前战局，不清除玩家养成。"""
        target_id, target_name = self._at_target(event)
        if not target_id:
            yield event.plain_result("要 @ 一个群友才能养哦。用法：/boss 养 @某人")
            return
        key = self._group_key(event)
        data = self._group_data(key)
        generation = int((data.get("boss") or {}).get("generation", 1))
        boss_data = engine.new_boss(
            target_id, target_name, initial_hp=self._initial_hp(), generation=generation
        )
        data["boss"] = boss_data
        data["fight"] = None
        self._touch(key)
        self._flush(force=True)
        yield event.plain_result(
            f"🐣 新 Boss 已就位：{target_name} · Lv1 · {flavor.boss_title(1)}"
            f" · 血量 {boss_data['max_hp']}\n旧战局已清空，/砍猪 开始新一轮围剿！"
        )

    @boss.command("rank", alias={"排行", "排行榜", "伤害榜", "输出"})
    async def rank_cmd(self, event: AstrMessageEvent):
        """/boss 排行 — 查看本轮对当前 Boss 的输出排行。"""
        key = self._group_key(event)
        data = self._group_data(key)
        rows = storage.ranking(data, self._ranking_size())
        boss_name = engine.boss_display_name(self._boss(data))
        body = format_rank_text(rows, boss_name)
        yield await self._panel_result(event, "本轮输出排行", body, build_rank_html(rows, boss_name))

    @boss.command("hall", alias={"名人堂", "历史"})
    async def hall_cmd(self, event: AstrMessageEvent):
        """/boss 名人堂 — 查看历代 Boss 的击杀、输出和耗时记录。"""
        data = self._group_data(self._group_key(event))
        rows = storage.hall_rows(data, self._ranking_size())
        yield await self._panel_result(event, "弑猪名人堂", format_hall_text(rows), build_hall_html(rows))

    @boss.command("me", alias={"我", "战报", "我的"})
    async def me_cmd(self, event: AstrMessageEvent):
        """/boss 我 — 查看个人战报、货币、猎手阶位、配装、称号与战斗加成。"""
        key = self._group_key(event)
        data = self._group_data(key)
        report = storage.player_report(data, self._sender_id(event) or "unknown", self._sender_name(event) or "群友")
        body = format_me_text(report, engine.boss_display_name(self._boss(data)))
        yield await self._panel_result(event, "我的战报", body, build_profile_html(report, engine.boss_display_name(self._boss(data))))

    @boss.command("shop", alias={"商店"})
    async def shop_cmd(self, event: AstrMessageEvent, view: str = "全览"):
        """/boss 商店 [全览|可买|武器|副手|护具|饰品|消耗品|金币|印记] — 一次查看完整或筛选商品。"""
        key = self._group_key(event)
        data = self._group_data(key)
        report = storage.player_report(data, self._sender_id(event) or "unknown", self._sender_name(event) or "群友")
        title, sections = economy.shop_sections(report, view)
        if not sections:
            yield event.plain_result("商店筛选无效。可用：全览、可买、武器、副手、护具、饰品、消耗品、金币、印记。")
            return
        body = format_shop_catalog_text(title, sections, report)
        try:
            url = await self.html_render(build_shop_catalog_html(title, sections, report), {})
            yield event.image_result(url)
        except Exception as e:
            logger.warning(f"cyber_boss 商店图卡渲染失败，回退纯文本: {e}")
            yield event.plain_result(body)

    @boss.command("buy", alias={"购买"})
    async def buy_cmd(self, event: AstrMessageEvent, item_id: str = "", quantity: int = 1):
        """/boss 购买 <商品ID|完整名称> [数量] — 按 ID 或完整名称购买装备、消耗品。"""
        key = self._group_key(event)
        ok, message, _ = storage.buy_item(
            self._group_data(key),
            self._sender_id(event) or "unknown",
            self._sender_name(event) or "群友",
            item_id,
            quantity,
        )
        if ok:
            self._touch(key)
        yield event.plain_result(message)

    @boss.command("bag", alias={"背包"})
    async def bag_cmd(self, event: AstrMessageEvent):
        """/boss 背包 — 查看背包、货币、四栏配装和已武装消耗品。"""
        key = self._group_key(event)
        report = storage.player_report(self._group_data(key), self._sender_id(event) or "unknown", self._sender_name(event) or "群友")
        body = format_inventory_text(report)
        yield await self._panel_result(event, "我的背包", body, build_inventory_html(report))

    @boss.command("equip", alias={"装备"})
    async def equip_cmd(self, event: AstrMessageEvent, item_id: str = ""):
        """/boss 装备 <商品ID|完整名称> — 将背包内装备穿到其对应栏位。"""
        key = self._group_key(event)
        ok, message, _ = storage.equip_item(self._group_data(key), self._sender_id(event) or "unknown", self._sender_name(event) or "群友", item_id)
        if ok:
            self._touch(key)
        yield event.plain_result(message)

    @boss.command("unequip", alias={"卸下"})
    async def unequip_cmd(self, event: AstrMessageEvent, slot: str = ""):
        """/boss 卸下 <武器|副手|护具|饰品> — 卸下指定装备栏。"""
        key = self._group_key(event)
        ok, message = storage.unequip_item(self._group_data(key), self._sender_id(event) or "unknown", self._sender_name(event) or "群友", slot)
        if ok:
            self._touch(key)
        yield event.plain_result(message)

    @boss.command("use", alias={"使用"})
    async def use_cmd(self, event: AstrMessageEvent, item_id: str = ""):
        """/boss 使用 <商品ID|完整名称> — 武装消耗品，在下一次实际结算 /砍猪 时消耗。"""
        key = self._group_key(event)
        ok, message, _ = storage.arm_consumable(self._group_data(key), self._sender_id(event) or "unknown", self._sender_name(event) or "群友", item_id)
        if ok:
            self._touch(key)
        yield event.plain_result(message)

    @boss.command("titles", alias={"称号"})
    async def titles_cmd(self, event: AstrMessageEvent):
        """/boss 称号 — 查看已解锁称号、效果与当前佩戴称号。"""
        key = self._group_key(event)
        report = storage.player_report(self._group_data(key), self._sender_id(event) or "unknown", self._sender_name(event) or "群友")
        body = format_titles_text(report)
        yield await self._panel_result(event, "称号收藏", body, build_titles_html(report))

    @boss.command("title", alias={"佩戴称号"})
    async def title_cmd(self, event: AstrMessageEvent, title_id: str = ""):
        """/boss 佩戴称号 <称号ID> — 从已解锁称号中选择一个生效。"""
        key = self._group_key(event)
        ok, message = storage.set_active_title(self._group_data(key), self._sender_id(event) or "unknown", self._sender_name(event) or "群友", title_id)
        if ok:
            self._touch(key)
        yield event.plain_result(message)

    async def terminate(self):
        self._flush(force=True)
        logger.info("cyber_boss 插件已停止")
