# battle_logic/constants.py
from enum import Enum

class Stat(Enum):
    HP = "hp"
    ATTACK = "attack"
    DEFENSE = "defense"
    SPECIAL_ATTACK = "special_attack"
    SPECIAL_DEFENSE = "special_defense"
    SPEED = "speed"
    ACCURACY = "accuracy"
    EVASION = "evasion"
    CRIT_RATE = "crit_rate"

class MoveCategory(Enum):
    PHYSICAL = "physical"
    SPECIAL = "special"
    STATUS = "status"

class BattleState(Enum):
    SELECTING = "selecting"
    FIGHTING = "fighting"
    AWAITING_SWITCH = "awaiting_switch"
    ENDED = "ended"

class TypeEffectiveness:
    @staticmethod
    def get_effectiveness(move_type: str, defender_types: list[str], chart: dict) -> float:
        """
        【已重构】计算属性克制倍率。
        现在从调用者接收克制表(chart)，而不是依赖于模块内的硬编码常量。
        
        Args:
            move_type: 攻击技能的属性。
            defender_types: 防御方的属性列表。
            chart: 从工厂获取的、完整的属性克制表字典。

        Returns:
            最终的伤害倍率。
        """
        e = 1.0
        # 使用传入的 chart 参数进行计算
        type_data = chart.get(move_type, {})
        for t in defender_types:
            if t in type_data.get("super_effective", []):
                e *= 2.0
            elif t in type_data.get("not_very_effective", []):
                e *= 0.5
            elif t in type_data.get("no_effect", []):
                return 0.0
        return e


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