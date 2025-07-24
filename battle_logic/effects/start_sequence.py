# battle_logic/effects/start_sequence.py (已修复日志缺失问题)

from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class StartSequenceEffect(BaseEffect):
    """
    效果处理器：启动一个追击序列。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        source_slot = next((slot for slot in attacker.skill_slots if slot.move is move), None)
        if source_slot is None:
            # 在测试或特殊情况下，move对象可能不是来自skill_slots，这可以接受
            return

        effect_id = f"sequence_slot_{source_slot.index}"
        sequence_id_from_json = self.effect_data.get("sequence_id")
        initial_charges = self.effect_data.get("initial_charges", 1)
        
        sequence_data = {
            "source_slot_index": source_slot.index,
            "sequence_id": sequence_id_from_json,
            "charges": initial_charges,
            "total_charges": initial_charges,
        }
        
        success, message, _ = attacker.apply_effect(
            effect_id=effect_id, 
            source_move=move.name, 
            options=sequence_data
        )

        # 【核心修复】确保即使 apply_effect 成功但 message 为空时，也有一条默认日志。
        # 这解决了 test_scenario_7 中击倒对手后日志不显示的问题。
        if success:
            prefix = self.battle._get_pokemon_log_prefix(attacker)
            if message:
                for line in message.split('\n'):
                    log.append(f"  {prefix}{attacker.name}{line.strip()}")
            else:
                 # apply_effect 对于刷新效果可能不返回message，这里提供默认日志
                log.append(f"  {prefix}{attacker.name}获得了 [序列效果] 效果！")