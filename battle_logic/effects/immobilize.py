# battle_logic/effects/immobilize.py

from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect

if TYPE_CHECKING:
    from ..pokemon import Pokemon
    from ..move import Move
    from ..battle import Battle

class ImmobilizeEffect(BaseEffect):
    """
    【最终版】效果处理器：使目标陷入“无法行动”状态一回合。
    这是一个通用的效果，可以被任何技能调用。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        # 从效果数据中确定目标
        target = attacker if self.effect_data.get("target", "opponent") == "opponent" else defender
        
        # 为目标设置一个临时的 'is_immobilized' 标志
        # 这个标志将在回合结束时被 battle.py 自动清除
        target.set_flag("is_immobilized", True)
        
        prefix = self.battle._get_pokemon_log_prefix(target)
        log.append(f"  {prefix}{target.name} 陷入了无法行动的状态！")
