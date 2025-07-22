# battle_logic/effects/base_effect.py
from abc import ABC, abstractmethod
from typing import List, Dict, TYPE_CHECKING, Any

# 【优化】不再需要从 battle 导入任何东西
if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move
    from ..battle import Battle

class BaseEffect(ABC):
    def __init__(self, battle: 'Battle', effect_data: Dict[str, Any]):
        """
        【核心重构】构造函数现在接收 Battle 实例，以实现依赖注入。
        """
        self.battle = battle
        self.effect_data = effect_data

    @abstractmethod
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        raise NotImplementedError