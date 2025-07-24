# battle_logic/components.py (已修正并最终确认)

from .aura import AuraComponent, ComponentLifespan
from .constants import Stat
from typing import Dict, Any, Optional

class StatusEffectComponent(AuraComponent):
    """组件：代表一个持续的异常状态或临时效果。"""
    def __init__(self, effect_id: str, properties: Dict[str, Any], **kwargs):
        """
        初始化状态效果组件。
        它的生命周期(lifespan)是动态的，将在pokemon.py的apply_effect方法中，
        根据效果的JSON属性(is_volatile, is_temporary)来决定并传入。
        """
        super().__init__(**kwargs)
        self.effect_id = effect_id
        self.name = properties.get('name', effect_id)
        self.properties = properties
        self.data: Dict[str, Any] = {}

class StatStageComponent(AuraComponent):
    """组件：代表一项能力等级的变化。"""
    def __init__(self, stat: Stat, change: int, **kwargs):
        # 【最终修正】能力等级是永久的，使用基类默认的 PERMANENT 生命周期。
        # 换下场时不会被清除。
        super().__init__(**kwargs)
        self.stat = stat
        self.change = change

class DamageComponent(AuraComponent):
    """组件：代表一次受到的伤害。"""
    def __init__(self, amount: int, is_direct: bool = True, **kwargs):
        # 伤害记录是永久的，使用默认生命周期
        super().__init__(**kwargs)
        self.amount = amount
        self.is_direct = is_direct

class HealComponent(AuraComponent):
    """组件：代表一次受到的治疗。"""
    def __init__(self, amount: int, **kwargs):
        # 治疗记录是永久的，使用默认生命周期
        super().__init__(**kwargs)
        self.amount = amount

class PPConsumptionComponent(AuraComponent):
    """组件：代表一次技能PP的消耗。"""
    def __init__(self, move_name: str, amount: int = 1, **kwargs):
        # PP消耗记录是永久的，使用默认生命周期
        super().__init__(**kwargs)
        self.move_name = move_name
        self.amount = amount

class VolatileFlagComponent(AuraComponent):
    """组件：代表一个临时的、一回合的标志（如'畏缩'）。"""
    def __init__(self, flag_id: str, **kwargs):
        # 回合结束时清除
        super().__init__(lifespan=ComponentLifespan.TEMPORARY, **kwargs)
        self.flag_id = flag_id

class CriticalBoostComponent(AuraComponent):
    """组件：代表一个暴击率提升的标志。"""
    def __init__(self, **kwargs):
        # 【最终修正】暴击提升效果是永久的，使用基类默认的 PERMANENT 生命周期。
        super().__init__(**kwargs)