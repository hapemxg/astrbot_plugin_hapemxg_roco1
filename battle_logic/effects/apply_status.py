# battle_logic/effects/apply_status.py (最终完整版)

from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect
from ..components import VolatileFlagComponent

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move
    from ..battle import Battle

class ApplyStatusEffect(BaseEffect):
    """
    【最终版】效果处理器：施加状态效果。
    这是一个通用的处理器，它将从JSON读取的效果ID、目标和附加选项(options)
    完全委托给 Pokemon 对象的 apply_effect 方法进行处理。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        """
        执行施加状态的逻辑。
        """
        effect_id = self.effect_data.get("status")
        if not effect_id:
            # 如果JSON中没有定义 'status' 字段，则静默失败，不产生日志
            return
            
        # 确定效果施加的目标
        target_str = self.effect_data.get("target", "opponent")
        target = defender if target_str == "opponent" else attacker
        
        # 为日志生成正确的前缀
        prefix = self.battle._get_pokemon_log_prefix(target)
        
        # --- 特殊情况处理：一次性的 VolatileFlag ---
        # 这种标志不通过 apply_effect，而是直接添加到Aura中
        props = self.battle.factory.get_effect_properties().get(effect_id, {})
        if props.get("category") == "volatile_flag":
            target.aura.add_component(VolatileFlagComponent(effect_id, source_move=move.name))
            # 从JSON读取自定义的施加日志
            apply_log = props.get('apply_log', f"获得了 [{props.get('name', effect_id)}] 效果！")
            log.append(f"  {prefix}{target.name}{apply_log}")
            return

        # --- 通用逻辑：委托给 pokemon.apply_effect ---
        # 从JSON效果定义中获取 'options' 字典
        options = self.effect_data.get("options")
        
        # 调用Pokemon对象的核心方法，将所有逻辑决策权交给它
        success, message, derivative_effects = target.apply_effect(
            effect_id=effect_id, 
            source_move=move.name, 
            options=options
        )
        
        # 根据 apply_effect 的返回结果生成日志
        if success:
            # message 可能包含多行，例如替换状态时的日志
            for line in message.split('\n'):
                log.append(f"  {prefix}{target.name}{line.strip()}")
            
            # 如果存在衍生效果，则立即通过 battle 实例递归执行它们
            if derivative_effects:
                self.battle.execute_effect_list(derivative_effects, attacker, target, move, log)
        else:
            # 如果施加失败，apply_effect 返回的 message 会包含原因
            log.append(f"  但它失败了... ({message})")