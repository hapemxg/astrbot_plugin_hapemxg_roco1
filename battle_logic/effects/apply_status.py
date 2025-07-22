# battle_logic/effects/apply_status.py
import random
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING: from ..pokemon import Pokemon, Move

class ApplyStatusEffect(BaseEffect):
    """
    【重构】效果处理器，能够处理并执行衍生效果。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        effect_id = self.effect_data.get("status")
        if not effect_id: return
            
        target = defender if self.effect_data.get("target", "opponent") == "opponent" else attacker
        
        penalty_info = self.effect_data.get("consecutive_use_penalty")
        success_chance = 100.0

        if penalty_info:
            history = self.battle.get_action_history_for(attacker) # 注意：这里应检查攻击者的历史
            past_history = history[1:]
            consecutive_count = 0
            move_to_check = penalty_info.get("move_name")
            for past_move in past_history:
                if past_move.name == move_to_check:
                    consecutive_count += 1
                else: break
            if consecutive_count > 0:
                reduction = consecutive_count * penalty_info.get("reduction_per_use", 20.0)
                success_chance = max(0, 100.0 - reduction)
        
        if random.uniform(0, 100) < success_chance:
            # 【修复】接收 apply_effect 返回的三个值
            success, message, derivative_effects = target.apply_effect(effect_id, source_move=move.name)
            
            if success:
                # 统一记录主效果的日志
                prefix = self.battle._get_pokemon_log_prefix(target)
                log.append(f"  {prefix}{target.name}{message}")
                
                # 【修复】如果存在衍生效果，则立即通过 battle 实例执行它们
                if derivative_effects:
                    # 注意：衍生效果的目标是原效果的目标(target)，但攻击者不变
                    self.battle.execute_effect_list(derivative_effects, attacker, target, move, log)
        elif penalty_info:
            log.append(f"  但它失败了...")