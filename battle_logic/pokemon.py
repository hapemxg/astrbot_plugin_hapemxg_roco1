# battle_logic/pokemon.py (已重构)
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Any, NamedTuple, TYPE_CHECKING

from .move import Move
from .constants import Stat, STAT_NAME_MAP
from .aura import Aura, ComponentLifespan
from .components import (
    StatusEffectComponent, StatStageComponent, DamageComponent,
    HealComponent, PPConsumptionComponent, VolatileFlagComponent,
    StatusImmunityComponent
)

if TYPE_CHECKING:
    from .factory import GameDataFactory

class SkillSlot(NamedTuple):
    index: int
    move: Move

class Pokemon:
    def __init__(
        self, name: str, level: int, types: List[str], stats: Dict[str, int],
        move_names: List[str], factory: "GameDataFactory", 
        innate_immunities: Optional[List[str]] = None
    ):
        self.name = name
        self.level = level
        self.types = types
        self.crit_points = stats.get("crit_points", 0)
        self.base_stats = stats
        self.factory = factory
        self.stats = self._calculate_stats(self.base_stats, self.level)
        self.max_hp = self.stats.get(Stat.HP, 1)
        self.skill_slots: List[SkillSlot] = []
        self._initialize_moves(move_names, factory)
        self.aura = Aura(self)
        self.aura.add_component(HealComponent(self.max_hp))

        if innate_immunities:
            immunity_comp = StatusImmunityComponent(
                immunity_id="innate",  # 为天生免疫提供一个固定的ID
                immune_to=innate_immunities, 
                lifespan=ComponentLifespan.PERMANENT
            )
            self.aura.add_component(immunity_comp)

    def _check_immunity(self, effect_id: str) -> Optional[str]:
        """
        【新增辅助方法】检查宝可梦是否对指定效果免疫。
        
        它会检查两种免疫来源：
        1. 由StatusImmunityComponent提供的免疫 (包括天生的和后天获得的)。
        2. 由其他状态效果的 "grants_immunity_to" 属性提供的临时免疫。

        Returns:
            如果免疫，则返回描述免疫原因的日志字符串；否则返回None。
        """
        # 1. 检查 StatusImmunityComponent
        immunity_components = self.aura.get_components(StatusImmunityComponent)
        for comp in immunity_components:
            if effect_id in comp.immune_to:
                source_name = f" [{comp.immunity_id}] 守护" if comp.immunity_id != "innate" else "天性"
                return f"但它因{source_name}而免疫了 [{effect_id}]！"

        # 2. 检查其他状态赋予的免疫
        active_statuses = self.aura.get_components(StatusEffectComponent)
        for status_comp in active_statuses:
            if effect_id in status_comp.properties.get("grants_immunity_to", []):
                return f"但它受到了 [{status_comp.name}] 的守护，免疫了 [{effect_id}]！"
        
        return None

    def _resolve_stacking_and_replacement(self, effect_id: str, new_props: Dict) -> Tuple[Optional[str], Optional[StatusEffectComponent]]:
        """
        【新增辅助方法】处理状态的叠加和替换逻辑。

        Returns:
            一个元组 (rejection_reason, effect_to_remove):
            - rejection_reason: 如果新效果因叠加规则被拒绝，则为拒绝原因。
            - effect_to_remove: 如果新效果需要替换掉一个旧效果，则为要被移除的旧效果组件。
        """
        existing_effect_by_id = self.get_effect(effect_id)
        stacking_behavior = new_props.get("stacking_behavior", "ignore")

        # 规则1: 如果同ID效果已存在，且叠加行为是'ignore'，则直接拒绝
        if existing_effect_by_id and stacking_behavior == "ignore":
            return f"已经处于 [{existing_effect_by_id.name}] 状态。", None

        # 规则2: 检查类型冲突
        effect_to_replace: Optional[StatusEffectComponent] = None
        new_status_type = new_props.get("status_type")
        if new_status_type:
            # 查找已存在的同类型效果
            existing_effect_of_type = next((c for c in self.aura.get_components(StatusEffectComponent) if c.properties.get("status_type") == new_status_type), None)
            if existing_effect_of_type:
                # 如果新旧效果ID不同，则标记旧效果为待替换
                if existing_effect_of_type.effect_id != effect_id:
                    effect_to_replace = existing_effect_of_type
                # 如果ID相同但不是刷新操作，则拒绝
                elif stacking_behavior != "refresh":
                    return f"已经处于 [{existing_effect_of_type.name}] 状态。", None
        
        # 规则3: 如果是刷新操作，标记同ID的旧效果为待替换
        if existing_effect_by_id and stacking_behavior == "refresh":
            effect_to_replace = existing_effect_by_id

        return None, effect_to_replace

    def _create_and_add_component(self, effect_id: str, new_props: Dict, source_move: Optional[str], options: Optional[Dict]) -> StatusEffectComponent:
        """
        【新增辅助方法】创建、配置并添加新的状态效果组件。
        """
        # 1. 决定生命周期
        lifespan = ComponentLifespan.PERMANENT
        if new_props.get("is_volatile"):
            lifespan = ComponentLifespan.VOLATILE
        elif new_props.get("is_temporary"):
            lifespan = ComponentLifespan.TEMPORARY
        
        # 2. 创建组件实例
        new_component = StatusEffectComponent(effect_id, new_props, source_move=source_move, lifespan=lifespan)
        
        # 3. 初始化运行时数据
        if new_props.get("ramping_damage"):
            new_component.data['toxic_counter'] = 1
        if options: 
            new_component.data.update(options)
            
        # 4. 添加到Aura
        self.aura.add_component(new_component)
        return new_component

    def apply_effect(
        self, effect_id: str, source_move: Optional[str] = None, options: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[List[Dict]]]:
        """
        【已重构】向宝可梦的Aura中施加一个状态效果。
        
        此方法现在是一个清晰的协调者，将复杂逻辑委托给多个辅助方法。
        流程:
        1. 委托 `_check_immunity` 进行免疫检查。
        2. 委托 `_resolve_stacking_and_replacement` 处理叠加/替换逻辑。
        3. 如果需要，移除旧效果。
        4. 委托 `_create_and_add_component` 创建并添加新组件。
        5. 构建日志并返回结果。
        """
        # 步骤 0: 获取效果属性
        new_props = self._get_effect_props(effect_id)
        if not new_props: 
            return False, f"系统错误：未知的效果ID '{effect_id}'", None

        # 步骤 1: 免疫检查 (Guard Clause)
        immunity_reason = self._check_immunity(effect_id)
        if immunity_reason:
            return False, immunity_reason, None

        # 步骤 2: 叠加/替换逻辑判断
        rejection_reason, effect_to_remove = self._resolve_stacking_and_replacement(effect_id, new_props)
        if rejection_reason:
            return False, rejection_reason, None

        # 步骤 3: 清理旧效果
        log_parts = []
        if effect_to_remove:
            removal_log = self._remove_effect_and_log(effect_to_remove.effect_id)
            if removal_log:
                log_parts.append(removal_log)

        # 步骤 4: 创建并添加新组件
        new_component = self._create_and_add_component(effect_id, new_props, source_move, options)

        # 步骤 5: 构建成功日志和衍生效果
        apply_log_template = new_props.get("apply_log", "获得了 [{name}] 效果！")
        log_parts.append(apply_log_template.format(name=new_component.name))
        
        final_log = "\n  ".join(log_parts)
        derivative_effects = new_props.get("on_apply_effects")
        return True, final_log, derivative_effects

    # --- 以下方法保持不变，仅为保持完整性而提供 ---

    @property
    def current_hp(self) -> int:
        damage = sum(c.amount for c in self.aura.get_components(DamageComponent))
        healed = sum(c.amount for c in self.aura.get_components(HealComponent))
        return max(0, min(self.max_hp, healed - damage))

    def is_fainted(self) -> bool:
        return self.current_hp <= 0

    def get_current_pp(self, move_name: str) -> Optional[int]:
        move = self.get_move_by_name(move_name)
        if move is None or move.max_pp is None: return None
        spent = sum(c.amount for c in self.aura.get_components(PPConsumptionComponent) if c.move_name == move_name)
        return move.max_pp - spent

    def get_modified_stat(self, stat: Stat) -> int:
        base = self.stats.get(stat, 1)
        stage = sum(c.change for c in self.aura.get_components(StatStageComponent) if c.stat == stat)
        mod = (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)
        val = base * mod
        for comp in self.aura.get_components(StatusEffectComponent):
            stat_mods = comp.properties.get("stat_modifiers")
            if stat_mods and stat.value in stat_mods:
                val *= stat_mods[stat.value]
        return math.floor(max(1, val))

    def has_usable_moves(self) -> bool:
        return any(s.move.max_pp is None or self.get_current_pp(s.move.name) > 0 for s in self.skill_slots)

    def has_effect(self, effect_id: str) -> bool:
        return any(c.effect_id == effect_id for c in self.aura.get_components(StatusEffectComponent))

    def get_effect(self, effect_id: str) -> Optional[StatusEffectComponent]:
        return next((c for c in self.aura.get_components(StatusEffectComponent) if c.effect_id == effect_id), None)

    def get_effects_by_category(self, category: str) -> List[StatusEffectComponent]:
        return [c for c in self.aura.get_components(StatusEffectComponent) if c.properties.get("category") == category]

    def take_damage(self, dmg: int, source_move: Optional[str] = None):
        self.aura.add_component(DamageComponent(dmg, source_move=source_move))

    def heal(self, amt: int, source_move: Optional[str] = None):
        self.aura.add_component(HealComponent(amt, source_move=source_move))

    def use_move(self, name: str):
        move = self.get_move_by_name(name)
        if move and move.max_pp is not None:
            self.aura.add_component(PPConsumptionComponent(name, source_move=name))

    def remove_effect(self, effect_id: str) -> bool:
        components = [c for c in self.aura.get_components(StatusEffectComponent) if c.effect_id == effect_id]
        if not components: return False
        for c in components: self.aura.remove_component(c)
        return True

    def apply_stat_change(self, stat: Stat, stages: int) -> Tuple[bool, str]:
        current = sum(c.change for c in self.aura.get_components(StatStageComponent) if c.stat == stat)
        new_total = max(-6, min(6, current + stages))
        change = new_total - current
        if change == 0:
            return False, f"的{STAT_NAME_MAP.get(stat)}已无法再{'提升' if stages > 0 else '降低'}！"
        self.aura.add_component(StatStageComponent(stat, change))
        msg = f"的{STAT_NAME_MAP.get(stat)}"
        if abs(change) >= 2: msg += "大幅"
        msg += "提升了！" if change > 0 else "降低了！"
        return True, msg

    def change_crit_stage(self, stages: int) -> Tuple[bool, str]:
        current = sum(c.change for c in self.aura.get_components(StatStageComponent) if c.stat == Stat.CRIT_RATE)
        new_total = max(0, min(3, current + stages))
        change = new_total - current
        if change == 0: return False, "的要害攻击率已无法再提升！"
        self.aura.add_component(StatStageComponent(Stat.CRIT_RATE, change))
        return True, "更容易击中要害了！"

    def purge_all_status_effects(self) -> List[str]:
        cleared_names = []
        components_to_remove = [
            c for c in self.aura.get_components(StatusEffectComponent) 
            if c.properties.get("category") == "status"
        ]
        for comp in components_to_remove:
            cleared_names.append(comp.name)
            self.aura.remove_component(comp)
        return cleared_names

    def purge_specific_effects(self, effect_ids: List[str]) -> List[str]:
        cleared_names = []
        components_to_remove = [
            c for c in self.aura.get_components(StatusEffectComponent) 
            if c.effect_id in effect_ids
        ]
        for comp in components_to_remove:
            cleared_names.append(comp.name)
            self.aura.remove_component(comp)
        return cleared_names

    def reset_negative_stages(self) -> Optional[str]:
        all_stages = self.aura.get_components(StatStageComponent)
        current_totals: Dict[Stat, int] = {}
        for comp in all_stages:
            current_totals[comp.stat] = current_totals.get(comp.stat, 0) + comp.change
        
        reset_stats = []
        for stat, total in current_totals.items():
            if total < 0:
                self.aura.add_component(StatStageComponent(stat, -total))
                if stat in STAT_NAME_MAP:
                    reset_stats.append(STAT_NAME_MAP[stat])
        
        if reset_stats:
            return f"被削弱的能力 ({'、'.join(reset_stats)}) 恢复到了正常水平！"
        return None

    def on_switch_out(self):
        self.aura.clear_components_by_lifespan(ComponentLifespan.VOLATILE)

    def clear_turn_effects(self):
        self.aura.clear_components_by_lifespan(ComponentLifespan.TEMPORARY)

    def _remove_effect_and_log(self, effect_id: str) -> Optional[str]:
        comp = self.get_effect(effect_id)
        if comp:
            self.aura.remove_component(comp)
            return comp.properties.get("remove_log", f"的 [{comp.name}] 效果消失了。")
        return None

    def _get_effect_props(self, effect_id: str) -> Dict:
        if effect_id.startswith("sequence_slot_"):
            return {"name": "序列效果", "category": "sequence", "stacking_behavior": "refresh"}
        return self.factory.get_effect_properties().get(effect_id, {})

    def _calculate_stats(self, base_stats: Dict[str, int], level: int) -> Dict[Stat, int]:
        IV, EV_TERM = 31, 0
        stats = {Stat.HP: math.floor(((2 * base_stats["hp"] + IV + EV_TERM) * level) / 100) + level + 10}
        stat_map = {"attack": Stat.ATTACK, "defense": Stat.DEFENSE, "special_attack": Stat.SPECIAL_ATTACK, "special_defense": Stat.SPECIAL_DEFENSE, "speed": Stat.SPEED}
        for key, stat_enum in stat_map.items():
            stats[stat_enum] = math.floor((((2 * base_stats[key] + IV + EV_TERM) * level) / 100) + 5)
        return stats

    def _initialize_moves(self, move_names: List[str], factory: 'GameDataFactory'):
        from astrbot.api import logger
        from copy import deepcopy
        for i, name in enumerate(move_names):
            template = factory.get_move_template(name)
            if template:
                self.skill_slots.append(SkillSlot(index=i, move=deepcopy(template)))
            else:
                logger.warning(f"未能为 {self.name} 加载技能 '{name}'.")

    def get_move_by_name(self, name: str) -> Optional[Move]:
        return next((s.move for s in self.skill_slots if s.move.name == name), None)