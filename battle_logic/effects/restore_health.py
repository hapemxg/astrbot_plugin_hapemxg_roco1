# battle_logic/effects/restore_health.py

from __future__ import annotations
import math
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class RestoreHealthEffect(BaseEffect):
    """
    【Aura架构版】效果处理器：恢复生命值。
    计算治疗量，然后调用目标的 heal 方法，
    该方法会将治疗记录为一个 HealComponent。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        target = attacker if self.effect_data.get("target") == "self" else defender
        
        if target.current_hp >= target.max_hp:
            log.append(f"  {self.battle._get_pokemon_log_prefix(target)}{target.name}的精力已经是满的了！")
            return

        percentage = self.effect_data.get("percentage", 0)
        if percentage > 0:
            heal_amount = math.floor(target.max_hp * (percentage / 100))
            old_hp = target.current_hp
            
            # 核心变化：调用pokemon上的方法，它会向Aura添加一个HealComponent
            target.heal(heal_amount, source_move=move.name)
            
            hp_log = f"[{old_hp} -> {target.current_hp}/{target.max_hp}]"
            log.append(f"  {self.battle._get_pokemon_log_prefix(target)}{target.name} 回复了 {heal_amount} 点精力！ {hp_log}")