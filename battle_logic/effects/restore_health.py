# battle_logic/effects/restore_health.py
import math
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon
    from ..move import Move
    from ..battle import Battle

class RestoreHealthEffect(BaseEffect):
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        # 根据技能数据决定是治疗自己还是对手
        target = attacker if self.effect_data.get("target") == "self" else defender
        owner_prefix = "你的" if target == self.battle.player_active_pokemon else "NPC的"
        
        percentage = self.effect_data.get("percentage", 0)
        
        if percentage > 0:
            if target.current_hp == target.max_hp:
                log.append(f"  {owner_prefix}{target.name}的精力已经是满的了！")
                return

            # 计算治疗量
            heal_amount = math.floor(target.max_hp * (percentage / 100))
            old_hp = target.current_hp
            
            # 执行治疗
            target.heal(heal_amount)
            
            # 记录日志
            hp_log = f"[{old_hp} -> {target.current_hp}/{target.max_hp}]"
            log.append(f"  {owner_prefix}{target.name} 回复了 {heal_amount} 点精力！ {hp_log}")
