# battle_logic/effects/deal_damage.py

from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect
from copy import copy

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class DealDamageEffect(BaseEffect):
    """
    【Aura架构版】效果处理器：造成伤害。
    它计算伤害值，然后调用目标的 take_damage 方法，
    该方法会将伤害记录为一个 DamageComponent。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        options = self.effect_data.get("options")
        if not options: return

        # 创建一个临时技能对象以支持动态的威力或类别
        temp_move = copy(move)
        temp_move.display_power = options.get("power", move.display_power)
        temp_move.category = options.get("category", move.category)
        
        # 通过注入的 battle 实例调用其伤害计算方法
        damage_result = self.battle.calculate_damage(attacker, defender, temp_move)
        
        damage = damage_result.get("damage", 0)
        damage_log = damage_result.get("log_msg", "")

        if damage > 0:
            # 核心变化：调用pokemon上的方法，它会向Aura添加一个DamageComponent
            defender.take_damage(damage, source_move=move.name)
            
            # 日志记录逻辑保持不变
            prefix = self.battle._get_pokemon_log_prefix(defender)
            log.append(f"  对 {prefix}{defender.name} 造成了 {damage} 点伤害！")
            if damage_log: log.append(f"  ({damage_log})")
        elif damage_log:
            # 处理“没有效果”等情况的日志
            log.append(f"  {damage_log}")