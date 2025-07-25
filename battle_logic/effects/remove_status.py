# battle_logic/effects/remove_status.py
from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class RemoveStatusEffect(BaseEffect):
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        effect_id = self.effect_data.get("status")
        if not effect_id: return
        target_str = self.effect_data.get("target", "self")
        target = attacker if target_str == "self" else defender
        
        # 【核心修改】调用能返回日志的方法，并处理日志
        removal_log = target._remove_effect_and_log(effect_id)
        if removal_log:
            prefix = self.battle._get_pokemon_log_prefix(target)
            log.append(f"  {prefix}{target.name}{removal_log}")