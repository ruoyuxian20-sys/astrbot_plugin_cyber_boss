"""群主养成计划插件：群主是全群共享 Boss，随手一刀，越砍越强。"""

from __future__ import annotations

import os
import random
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core import engine, flavor, storage
from .core.render import (
    build_boss_html,
    format_attack_text,
    format_hall_text,
    format_kill_text,
    format_me_text,
    format_rank_text,
    format_status_text,
)

_HELP_TEXT = """⚔️ 群主养成计划 · 玩法说明

/砍
    随手一刀：可能暴击、被闪避、被反击住院、心软给 Boss 回血、掏出神器
/boss 状态
    查看 Boss 血条、等级、称号与本轮战况
/boss 养 @某人
    换养一个新 Boss（任意群友），从 Lv1 重新开始养成；仅机器人管理员可操作
/boss 排行
    本轮对 Boss 的输出排行
/boss 名人堂
    历代弑主者记录
/boss 我
    个人战报与称号
/boss 帮助
    查看本说明

Boss 血量清零即被击杀：击杀者获「弑主者」称号，
本轮输出第一授「主力输出」；随后 Boss 升级复活、血量 +20%，
越砍越强——这就是养成。
纯属娱乐，请勿真的攻击群主。"""

_GROUP_WORDS = {"boss", "群主", "养成"}
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


class CyberBoss(Star):
    """群主养成计划：全群共斗养成小游戏，不调用 LLM。"""

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
            path = os.path.join(self._data_dir(), f"{key}.json")
            data = storage.load_group_data(path)
            self._groups[key] = data
        return data

    def _boss(self, data: dict) -> dict:
        """取当前 Boss；没有则生成第 1 代虚拟群主。"""
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
        base = self._data_dir()
        for key in list(self._dirty):
            try:
                storage.save_group_data(
                    os.path.join(base, f"{key}.json"),
                    self._groups.get(key, storage.empty_group()),
                )
            except Exception as e:
                logger.warning(f"cyber_boss 保存群数据失败 {key}: {e}")
        self._dirty.clear()
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

    # ---------- 核心动作：/砍 ----------

    @filter.command("砍", alias={"打", "攻击"})
    async def slash_cmd(self, event: AstrMessageEvent):
        """砍 Boss 一刀：伤害随机，暴击/闪避/反击/心软/神器都有可能"""
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

        result = engine.attack(self._rng, boss, name, hp_growth=self._hp_growth())
        player = storage.record_attack(data, uid, name, result, now=now)
        if result.kind == "counter":
            self._hospital[pkey] = now + self._hospital_seconds()
        self._cooldown[pkey] = now

        if result.killed:
            entry = storage.settle_kill(data, uid, name, result, now=now)
            data["boss"] = result.boss
            self._touch(key)
            self._flush(force=True)
            yield event.plain_result(
                format_kill_text(result, result.boss, name, entry, rng=self._rng)
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
        if result.kind == "counter":
            body_parts.append(f"⏳ 住院 {self._hospital_seconds()} 秒后再战")
        gained = [
            flavor.PLAYER_TITLES.get(t, t)
            for t in player.get("titles", [])
            if t not in prev_titles
        ]
        if gained:
            body_parts.append(f"🏅 解锁称号：「{'」、「'.join(gained)}」")
        yield event.plain_result("\n".join(body_parts))

    # ---------- 命令组 ----------

    @filter.command_group("boss", alias={"群主", "养成"})
    def boss():
        """群主养成计划：/boss 状态|养|排行|名人堂|我|帮助"""

    @boss.command("help", alias={"帮助", "菜单"})
    async def help_cmd(self, event: AstrMessageEvent):
        """查看群主养成计划使用说明"""
        yield event.plain_result(_HELP_TEXT)

    @boss.command("status", alias={"状态", "血条", "查看"})
    async def status_cmd(self, event: AstrMessageEvent):
        """查看 Boss 血条、等级、称号与本轮战况"""
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
        """换养新 Boss（仅机器人管理员可操作）。用法：/boss 养 @某人"""
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
            f" · 血量 {boss_data['max_hp']}\n旧战局已清空，/砍 开始新一轮围剿！"
        )

    @boss.command("rank", alias={"排行", "排行榜", "伤害榜", "输出"})
    async def rank_cmd(self, event: AstrMessageEvent):
        """本轮对 Boss 的输出排行"""
        key = self._group_key(event)
        data = self._group_data(key)
        rows = storage.ranking(data, self._ranking_size())
        yield event.plain_result(
            format_rank_text(rows, engine.boss_display_name(self._boss(data)))
        )

    @boss.command("hall", alias={"名人堂", "历史"})
    async def hall_cmd(self, event: AstrMessageEvent):
        """历代弑主者记录"""
        data = self._group_data(self._group_key(event))
        rows = storage.hall_rows(data, self._ranking_size())
        yield event.plain_result(format_hall_text(rows))

    @boss.command("me", alias={"我", "战报", "我的"})
    async def me_cmd(self, event: AstrMessageEvent):
        """个人战报与称号"""
        key = self._group_key(event)
        data = self._group_data(key)
        report = storage.player_report(data, self._sender_id(event) or "unknown")
        yield event.plain_result(
            format_me_text(report, engine.boss_display_name(self._boss(data)))
        )

    async def terminate(self):
        self._flush(force=True)
        logger.info("cyber_boss 插件已停止")
