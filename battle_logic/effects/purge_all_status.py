# battle_logic/effects/purge_all_status.py
from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class PurgeAllStatusEffect(BaseEffect):
    """
    【升级版】效果处理器：
    - 如果配置了 purge_list，则只清除列表中的异常状态。
    - 如果未配置 purge_list，则清除目标身上所有类别为'status'的异常状态。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        target = attacker if self.effect_data.get("target") == "self" else defender
        
        # 从技能配置中读取要净化的列表
        effects_to_purge = self.effect_data.get("purge_list")
        
        cleared_names: List[str] = []
        if effects_to_purge and isinstance(effects_to_purge, list):
            # 场景 A: 只净化指定的异常
            cleared_names = target.purge_specific_effects(effects_to_purge)
        else:
            # 场景 B: 净化所有'status'类别的异常 (保持原有功能)
            cleared_names = target.purge_all_status_effects()
        
        if cleared_names:
            prefix = self.battle._get_pokemon_log_prefix(target)
            if effects_to_purge:
                # 为指定净化提供更精确的日志
                log.append(f"  {prefix}{target.name}的 [{', '.join(cleared_names)}] 效果被净化了！")
            else:
                log.append(f"  {prefix}{target.name}身上的所有异常状态都被净化了！")