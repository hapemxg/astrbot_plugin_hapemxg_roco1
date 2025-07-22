# battle_logic/effects/deal_damage.py
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect
from copy import copy

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class DealDamageEffect(BaseEffect):
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        options = self.effect_data.get("options")
        if not options: return

        temp_move = copy(move)
        temp_move.display_power = options.get("power", move.display_power)
        
        # 【核心修复】从 options 中获取技能类别，覆盖临时技能的默认值
        temp_move.category = options.get("category", move.category)
        
        # 通过注入的 battle 实例调用其方法
        damage_result = self.battle.calculate_damage(attacker, defender, temp_move)
        
        damage = damage_result.get("damage", 0)
        damage_log = damage_result.get("log_msg", "")

        if damage > 0:
            defender.take_damage(damage)
            prefix = self.battle._get_pokemon_log_prefix(defender)
            log.append(f"  对 {prefix}{defender.name} 造成了 {damage} 点伤害！")
            if damage_log: log.append(f"  ({damage_log})")
        elif damage_log:
            log.append(f"  {damage_log}")