"""文案库：本插件好玩程度的核心。全部为纯数据，占位符 {boss} {player}。"""

from __future__ import annotations

# ---------- 普通命中（每次砍一刀都配一句，保证不无聊） ----------

HIT_QUIPS = [
    "{player} 一记手刀砍在 {boss} 的尊严上",
    "{player} 抄起聊天气泡糊了 {boss} 一脸",
    "{player} 对 {boss} 使出了「已读乱回」，命中要害",
    "{player} 一巴掌拍散了 {boss} 刚打的一段字",
    "{player} 用手机支架夹了 {boss} 一下",
    "{player} 往 {boss} 的输入框里塞了一把瓜子壳",
    "{player} 顺手薅了 {boss} 一根头发",
    "{player} 一拳打在 {boss} 的流量包上",
    "{player} 对 {boss} 念了一段群规，字字扎心",
    "{player} 拿充电线当鞭子抽了 {boss} 一下",
    "{player} 把 {boss} 的表情包截了个图当武器",
    "{player} 一脚踩住了 {boss} 的正在输入",
]

# ---------- 暴击（配沙雕武器） ----------

# name: 武器名，verb: 打击动作描述
CRIT_WEAPONS = [
    {"name": "祖传键盘", "verb": "劈头盖脸砸了下去"},
    {"name": "冰红茶", "verb": "整瓶泼了过去，还是常温的"},
    {"name": "人字拖", "verb": "脱下来精准命中后脑勺"},
    {"name": "半块板砖", "verb": "拍出了人生的重量"},
    {"name": "蓝牙音箱", "verb": "外放《大悲咒》完成超度"},
    {"name": "60 秒语音", "verb": "连发三条轰了过去"},
    {"name": "一张数学卷", "verb": "拍在桌上，附加精神创伤"},
    {"name": "代码 Review 意见", "verb": "逐条念了出来，句句诛心"},
    {"name": "烫嘴的外卖", "verb": "连汤带面扣了上去"},
    {"name": "周一早晨的闹钟", "verb": "连环 call 了七遍"},
    {"name": "会议邀请链接", "verb": "甩过去并要求开摄像头"},
    {"name": "一张三年前的聊天记录截图", "verb": "缓缓展开，杀气扑面"},
    {"name": "电量 1% 的手机", "verb": "掷了出去，破釜沉舟"},
    {"name": "键盘上抠下来的 Alt 键", "verb": "当作暗器弹射而出"},
]

# ---------- 闪避（Boss 躲开了） ----------

DODGE_LINES = [
    "{boss} 已读不回，攻击落了空",
    "{boss} 切了个小号，攻击打在了空气上",
    "{boss} 假装在忙，实际正在潜水，没砍到",
    "攻击被 {boss} 的「消息过滤」吞掉了",
    "{boss} 用一句「网络卡了」挡下了这记重击",
    "{boss} 刚刚开启了免打扰，物理免疫",
    "{player} 砍了个寂寞",
    "{boss} 一个滑铲躲进了群相册",
    "{boss} 潜入深海，水面只留下一串气泡",
]

# ---------- 反击（玩家被打住院） ----------

COUNTER_LINES = [
    "{boss} 反手一个禁言，{player} 被送进小黑屋住院观察",
    "{boss} 甩出三段 60 秒语音，{player} 当场昏厥",
    "{boss} 发动「撤回」，连 {player} 刚才的攻击一起撤回了",
    "{boss} @了全体成员，{player} 被声波震伤",
    "{boss} 发了个红包，{player} 抢到 0.01 元，气到住院",
    "{boss} 深度潜水三年，一出手就是雷霆之势，{player} 倒飞出去",
    "{boss} 甩出会议链接，{player} 被迫听了一小时周报",
    "{boss} 把 {player} 移出了群聊（梦里），精神重创",
    "{boss} 冷冷回了句「？」，{player} 心态崩了",
]

# ---------- 心软（给 Boss 回血） ----------

MERCY_LINES = [
    "{player} 突然想起 {boss} 发过红包，手一软，{boss} 回了口血",
    "{boss} 无辜的眼神让 {player} 下不去手，甚至想给他倒杯水",
    "{player} 砍到一半想起 {boss} 上次帮自己说过话，改成了抚摸，{boss} 气血回暖",
    "{boss} 连发了三个「在吗」，{player} 不忍心了",
    "{player} 看清了 {boss} 的头像是只小猫，做不到，{boss} 趁机回血",
    "{boss} 说了句「最近有点累」，{player} 的刀停在了半空",
]

# ---------- 神器（巨额伤害） ----------

ARTIFACT_LINES = [
    "{player} 掏出了祖传的 main.py——没有注释的那种，{boss} 目睹后灵魂受创",
    "{player} 翻出了三年前的聊天记录，句句是刀，{boss} 直接跪了",
    "{player} 祭出「已读乱回」终极形态，{boss} 的世界观被击穿",
    "{player} 放出了收藏夹里 800 个从未看完的教程，知识就是力量",
    "{player} 甩出了那份没有截止日期的需求文档，{boss} 当场石化",
    "{player} 把 Windows 更新弹窗拍在了 {boss} 脸上，且点了「稍后提醒」",
    "{player} 召唤了周一早八的闹钟大军，{boss} 节节败退",
    "{player} 念出了 {boss} 曾立过又没兑现的 Flag 全文，天雷滚滚",
]

# ---------- Boss 称号阶梯（level >= 对应值取最大命中档） ----------

BOSS_TITLE_LADDER = [
    (1, "新手小猪"),
    (2, "已读不回猪仔"),
    (3, "深海潜航猪"),
    (4, "红包沉默猪"),
    (5, "已读不回猪王"),
    (6, "禁言收割猪"),
    (7, "赛博护城猪"),
    (8, "全群猪敌"),
    (10, "传说·满级猪王"),
    (15, "赛博暴猪"),
    (20, "永恒猪神"),
]


def boss_title(level: int) -> str:
    """按 Boss 等级返回称号；阶梯必须升序。"""
    title = BOSS_TITLE_LADDER[0][1]
    for floor, name in BOSS_TITLE_LADDER:
        if level >= floor:
            title = name
        else:
            break
    return title


# ---------- 玩家称号（成就判定在 engine，文案在此） ----------

PLAYER_TITLES = {
    "top_dps": "主力输出",
    "filial": "小猪孝子",
    "hospitalized": "住院常客",
    "coder": "代码术士",
}


def regicide_title(kills: int) -> str:
    """弑猪者称号随击杀数升级。"""
    return f"弑猪者Lv{max(1, kills)}"


# ---------- 击杀播报 ----------

KILL_HEADER = [
    "💥 老板，{boss} 倒下了！",
    "🏆 经此一役，{boss} 光荣下班！",
    "🗡️ 补刀成功，{boss} 应声倒地！",
]

REVIVE_LINES = [
    "{boss} 原地复活了，等级 +1，血量 +20%——这就是养成",
    "{boss} 从倒下的地方爬了起来，眼神里多了几分沧桑",
    "一阵金光过后，{boss} 满血归来，还有点小强",
    "{boss} 掸了掸灰：「就这？」（血量涨了 20%）",
]

ENRAGE_LINES = [
    "🔥 {boss} 进入了狂暴状态，反击欲望高涨！",
    "🔥 血量告急，{boss} 红温了，谁都别想好好走开",
]

# ---------- 开战（本轮第一刀） ----------

FIRST_BLOOD_LINES = [
    "⚔️ {player} 对 {boss} 打响了第一枪！",
    "⚔️ {player} 拔刀了，{boss} 的养成之路开始了",
    "⚔️ {player} 先动手了，全群跟上！",
]
