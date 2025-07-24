# battle_logic/effects/stat_change.py

from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect
from ..constants import Stat

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class StatChangeEffect(BaseEffect):
    """
    【Aura架构版】效果处理器：改变能力或暴击等级。
    调用目标宝可梦的专用方法，这些方法现在负责向Aura添加StatStageComponent。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        target = attacker if self.effect_data.get("target") == "self" else defender
        
        for change_info in self.effect_data.get("changes", []):
            try:
                stat_to_change = Stat(change_info["stat"])
                change_amount = change_info["change"]

                # 根据属性类型，调用Pokemon对象上对应的专用方法
                if stat_to_change == Stat.CRIT_RATE:
                    success, message = target.change_crit_stage(change_amount)
                else:
                    success, message = target.apply_stat_change(stat_to_change, change_amount)

                if message:
                    log.append(f"  {message}")

            except (ValueError, KeyError):
                log.append(f"（系统警告：在moves.json中发现无效的stat名称 '{change_info.get('stat')}'）")