# battle_logic/aura.py

from abc import ABC
from typing import List, Type, TypeVar, Optional, TYPE_CHECKING
import weakref
from enum import Enum, auto

if TYPE_CHECKING:
    from .pokemon import Pokemon

T = TypeVar('T', bound='AuraComponent')

# 【新增】定义组件的生命周期
class ComponentLifespan(Enum):
    PERMANENT = auto()      # 永久，直到被特定效果治愈 (如：中毒、烧伤、能力等级)
    VOLATILE = auto()       # 挥发性，换下场时清除 (如：诅咒)
    TEMPORARY = auto()      # 临时性，回合结束时清除 (如：畏缩、守住标志)

class AuraComponent(ABC):
    """
    状态偏差组件的抽象基类。
    每个组件代表对宝可梦原始状态的一种修改。
    """
    def __init__(self, source_move: Optional[str] = None, lifespan: ComponentLifespan = ComponentLifespan.PERMANENT):
        """
        初始化组件。

        Args:
            source_move (Optional[str], optional): 效果的来源技能名称。
            lifespan (ComponentLifespan, optional): 组件的生命周期，默认为永久。
        """
        self.source_move = source_move
        self.lifespan = lifespan

class Aura:
    """
    封装宝可梦所有状态偏差的容器。
    它负责管理所有附加到宝可梦身上的AuraComponent。
    """
    def __init__(self, owner: 'Pokemon'):
        self._owner_ref = weakref.ref(owner)
        self._components: List[AuraComponent] = []

    @property
    def owner(self) -> 'Pokemon':
        """安全地获取所属的宝可梦实例。"""
        owner = self._owner_ref()
        if owner is None:
            raise RuntimeError("Aura's owner has been garbage collected.")
        return owner

    def add_component(self, component: AuraComponent):
        """向气场中添加一个新的状态组件。"""
        self._components.append(component)

    def get_components(self, component_type: Type[T]) -> List[T]:
        """获取所有指定类型的组件。"""
        return [comp for comp in self._components if isinstance(comp, component_type)]

    def remove_component(self, component: AuraComponent):
        """移除一个指定的组件实例。"""
        if component in self._components:
            self._components.remove(component)

    def clear_components_by_lifespan(self, lifespan_to_clear: ComponentLifespan):
        """
        【核心重构】根据生命周期清除组件。
        这是实现开闭原则的关键，所有清理逻辑都集中于此，
        使得Pokemon类无需关心具体的组件类型。
        """
        self._components = [c for c in self._components if c.lifespan != lifespan_to_clear]