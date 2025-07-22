# battle_logic/effects/start_sequence.py
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING: from ..pokemon import Pokemon, Move

class StartSequenceEffect(BaseEffect):
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        """【最终版】以技能槽索引为ID，启动或刷新一个精确的序列效果。"""
        source_slot = next((slot for slot in attacker.skill_slots if slot.move is move), None)
        if source_slot is None: return

        effect_id = f"sequence_slot_{source_slot.index}"
        
        sequence_id_from_json = self.effect_data.get("sequence_id")
        initial_charges = self.effect_data.get("initial_charges", 1)
        
        # 【核心修改】在数据中加入'is_activation_turn'标记
        sequence_data = {
            "source_slot_index": source_slot.index,
            "sequence_id": sequence_id_from_json,
            "charges": initial_charges,
            "total_charges": initial_charges,
            "is_activation_turn": True  # <-- “门闩”标记
        }
        
        # 施加或刷新效果（pokemon.py的apply_effect已有刷新逻辑）
        attacker.apply_effect(
            effect_id=effect_id, 
            source_move=move.name, 
            options=sequence_data
        )
        # 注意：施加效果本身的日志由pokemon.py处理，这里不再重复记录