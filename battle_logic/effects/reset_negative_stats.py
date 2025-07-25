# battle_logic/effects/reset_negative_stats.py
from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class ResetNegativeStatsEffect(BaseEffect):
    """
    【新增】效果处理器：重置目标所有为负的能力等级至0。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        target = attacker if self.effect_data.get("target") == "self" else defender

        # 调用将在 Pokemon 类中实现的新方法
        log_message = target.reset_negative_stages()
        
        if log_message:
            prefix = self.battle._get_pokemon_log_prefix(target)
            log.append(f"  {prefix}{target.name}{log_message}")