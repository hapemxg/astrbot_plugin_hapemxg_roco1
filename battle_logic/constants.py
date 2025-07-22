# battle_logic/constants.py
from enum import Enum

class Stat(Enum):
    HP = "hp"; ATTACK = "attack"; DEFENSE = "defense"; SPECIAL_ATTACK = "special_attack"
    SPECIAL_DEFENSE = "special_defense"; SPEED = "speed"; ACCURACY = "accuracy"; EVASION = "evasion"; CRIT_RATE = "crit_rate"

class MoveCategory(Enum):
    PHYSICAL = "physical"; SPECIAL = "special"; STATUS = "status"

class BattleState(Enum):
    SELECTING = "selecting"; FIGHTING = "fighting"; AWAITING_SWITCH = "awaiting_switch"; ENDED = "ended"

TYPE_CHART = {
    "水": {"super_effective": ["火"], "not_very_effective": ["草"], "no_effect": []},
    "火": {"super_effective": ["草"], "not_very_effective": ["水"], "no_effect": []},
    "草": {"super_effective": ["水"], "not_very_effective": ["火", "草"], "no_effect": []},
    "一般": {"super_effective": [], "not_very_effective": [], "no_effect": ["幽灵"]},
    "幽灵": {"super_effective": [], "not_very_effective": [], "no_effect": ["一般"]},
}

class TypeEffectiveness:
    @staticmethod
    def get_effectiveness(move_type: str, defender_types: list[str]) -> float:
        e = 1.0; chart = TYPE_CHART.get(move_type, {})
        for t in defender_types:
            if t in chart.get("super_effective", []): e *= 2.0
            elif t in chart.get("not_very_effective", []): e *= 0.5
            elif t in chart.get("no_effect", []): return 0.0
        return e

# --- 最终版效果定义注册表 ---
EFFECT_PROPERTIES = {
    # --- 分区1: 核心异常状态 (category: "status") ---
    # A类 (同一时间只能存在一个A类)
    "poison":    {"name": "中毒", "category": "status", "status_type": "A", "is_volatile": False, "stacking_behavior": "ignore", "damage_per_turn": 0.125},
    "curse":     {"name": "诅咒", "category": "status", "status_type": "A", "is_volatile": True, "stacking_behavior": "ignore", "damage_per_turn": 0.25},

    # B类 (同一时间只能存在一个B类)
    "burn":      {"name": "灼伤", "category": "status", "status_type": "B", "is_volatile": False, "stacking_behavior": "ignore", "damage_per_turn": 0.0625, "stat_modifiers": {Stat.ATTACK: 0.5}},
    "paralysis": {"name": "麻痹", "category": "status", "status_type": "B", "is_volatile": False, "stacking_behavior": "ignore", "stat_modifiers": {Stat.SPEED: 0.5}, "immobility_chance": 0.25},
    "sleep":     {"name": "睡眠", "category": "status", "status_type": "B", "is_volatile": False, "stacking_behavior": "ignore", "max_duration": 3, "blocks_action": True},
    "freeze":    {"name": "冰冻", "category": "status", "status_type": "B", "is_volatile": False, "stacking_behavior": "ignore", "clear_chance": 0.2, "blocks_action": True},
    "confusion": {"name": "混乱", "category": "status", "status_type": "B", "is_volatile": True, "stacking_behavior": "ignore", "max_duration": 4, "self_hit_chance": 0.33},
    "fear":      {"name": "恐惧", "category": "status", "status_type": "B", "is_volatile": True, "stacking_behavior": "ignore", "on_apply_effects": [{"handler": "apply_status", "status": "flinch", "chance": 100}]},

    # C类 (同一时间只能存在一个C类)
    "bind":      {"name": "束缚", "category": "status", "status_type": "C", "is_volatile": True, "stacking_behavior": "ignore", "damage_per_turn": 0.125, "blocks_switch": True, "max_duration": 5},

    # --- 分区2: 临时效果 (category: "marker") ---
    "flinch":    {"name": "畏缩", "category": "marker", "is_volatile": True, "stacking_behavior": "refresh", "blocks_action": True, "lifespan": "turn"},
    "evasion_shield": {"name": "闪避架势", "category": "marker", "is_volatile": True, "stacking_behavior": "refresh", "guaranteed_evasion": True, "lifespan": "turn"},
    
    # --- 分区3: 序列效果 (category: "sequence") ---
    # 这个条目是可选的，因为序列效果的行为主要在 pokemon.py 和 battle.py 中动态处理
    # 但保留它可以用于类型检查或未来的扩展
    "sequence_effect": {"name": "序列效果", "category": "sequence", "is_volatile": True, "stacking_behavior": "refresh"},
}

STAT_NAME_MAP = {
    Stat.ATTACK: "攻击",
    Stat.DEFENSE: "防御",
    Stat.SPECIAL_ATTACK: "特攻",
    Stat.SPECIAL_DEFENSE: "特防",
    Stat.SPEED: "速度",
    Stat.ACCURACY: "命中率",
    Stat.EVASION: "闪避率",
    Stat.CRIT_RATE: "暴击等级"
}