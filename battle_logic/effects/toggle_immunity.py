# battle_logic/effects/toggle_immunity.py
from __future__ import annotations
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect
from ..components import StatusImmunityComponent, ComponentLifespan

if TYPE_CHECKING:
    from ..pokemon import Pokemon, Move

class ToggleImmunityEffect(BaseEffect):
    """
    【新增】效果处理器：切换（开启/关闭）一个指定的免疫效果。
    
    工作逻辑:
    1. 检查目标身上是否已存在具有特定`immunity_id`的组件。
    2. 如果存在，则将其移除（关闭效果）。
    3. 如果不存在，则根据配置创建一个新的并施加（开启效果）。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        target = attacker if self.effect_data.get("target") == "self" else defender
        prefix = self.battle._get_pokemon_log_prefix(target)
        
        # 从技能配置中获取这个免疫效果的唯一标识符
        immunity_id = self.effect_data.get("immunity_id")
        if not immunity_id:
            # 如果没有配置ID，则无法工作
            return

        # 查找是否已存在该免疫组件
        existing_comp = next((c for c in target.aura.get_components(StatusImmunityComponent) if c.immunity_id == immunity_id), None)

        if existing_comp:
            # --- 场景A: 效果已存在，执行“关闭”逻辑 ---
            target.aura.remove_component(existing_comp)
            # 从配置中读取关闭时的日志
            remove_log = self.effect_data.get("remove_log", f"的 [{immunity_id}] 守护消失了。")
            log.append(f"  {prefix}{target.name}{remove_log}")
        else:
            # --- 场景B: 效果不存在，执行“开启”逻辑 ---
            immunities_to_apply = self.effect_data.get("immunities", [])
            
            # 决定生命周期，默认为VOLATILE（换人消失）
            lifespan_str = self.effect_data.get("lifespan", "volatile").upper()
            lifespan = getattr(ComponentLifespan, lifespan_str, ComponentLifespan.VOLATILE)

            new_comp = StatusImmunityComponent(
                immunity_id=immunity_id,
                immune_to=immunities_to_apply,
                lifespan=lifespan,
                source_move=move.name
            )
            target.aura.add_component(new_comp)
            
            # 从配置中读取开启时的日志
            apply_log = self.effect_data.get("apply_log", f"被 [{immunity_id}] 守护着！")
            log.append(f"  {prefix}{target.name}{apply_log}")