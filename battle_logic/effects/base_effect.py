# battle_logic/effects/base_effect.py

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move
    from ..battle import Battle

class BaseEffect(ABC):
    """
    效果处理器的抽象基类。
    【Aura架构版】构造函数接收Battle实例，以实现依赖注入。
    子类通过操作宝可夢的Aura来执行效果。
    """
    def __init__(self, battle: 'Battle', effect_data: Dict[str, Any]):
        self.battle = battle
        self.effect_data = effect_data

    @abstractmethod
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        raise NotImplementedError