# battle_logic/pokemon.py (拨乱反正版)
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Any, NamedTuple, TYPE_CHECKING

from .move import Move
from .constants import Stat, STAT_NAME_MAP
from .aura import Aura, ComponentLifespan
from .components import (
    StatusEffectComponent, StatStageComponent, DamageComponent,
    HealComponent, PPConsumptionComponent, VolatileFlagComponent
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

    def apply_effect(
        self, effect_id: str, source_move: Optional[str] = None, options: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[List[Dict]]]:
        """【最终修复版】施加状态效果，具有清晰的决策流程。"""
        new_props = self._get_effect_props(effect_id)
        if not new_props: return False, f"未知效果: {effect_id}", None

        # --- 1. 决策阶段：检查是否可以施加 ---
        existing_effect_by_id = self.get_effect(effect_id)
        stacking_behavior = new_props.get("stacking_behavior", "ignore")

        if existing_effect_by_id and stacking_behavior == "ignore":
            return False, f"已经处于 [{existing_effect_by_id.name}] 状态。", None

        effect_to_replace_by_type: Optional[StatusEffectComponent] = None
        new_status_type = new_props.get("status_type")
        if new_status_type:
            effect_to_replace_by_type = next((c for c in self.aura.get_components(StatusEffectComponent) if c.properties.get("status_type") == new_status_type), None)
            # 如果存在同类型状态，且不是同一个效果（即不是刷新自己），则通常不允许叠加
            if effect_to_replace_by_type and effect_to_replace_by_type.effect_id != effect_id:
                pass # 允许替换
            elif effect_to_replace_by_type and effect_to_replace_by_type.effect_id == effect_id and stacking_behavior != "refresh":
                 # 存在同ID同TYPE的状态，但不是刷新模式，则按之前的ignore逻辑处理（理论上已被上面捕获）
                 return False, f"已经处于 [{effect_to_replace_by_type.name}] 状态。", None

        # --- 2. 执行阶段：清理旧状态 ---
        log_parts = []
        if existing_effect_by_id and stacking_behavior == "refresh":
            self.remove_effect(effect_id) # 刷新自己

        if effect_to_replace_by_type and effect_to_replace_by_type.effect_id != effect_id:
            removal_log = self._remove_effect_and_log(effect_to_replace_by_type.effect_id)
            if removal_log:
                log_parts.append(removal_log)

        # --- 3. 施加新效果 ---
        lifespan = ComponentLifespan.PERMANENT
        if new_props.get("is_volatile"): lifespan = ComponentLifespan.VOLATILE
        elif new_props.get("is_temporary"): lifespan = ComponentLifespan.TEMPORARY
        
        new_component = StatusEffectComponent(effect_id, new_props, source_move=source_move, lifespan=lifespan)
        if options: new_component.data.update(options)
        self.aura.add_component(new_component)

        # --- 4. 生成最终日志 ---
        apply_log_template = new_props.get("apply_log", "获得了 [{name}] 效果！")
        log_parts.append(apply_log_template.format(name=new_component.name))
        
        final_log = "\n  ".join(log_parts)
        derivative_effects = new_props.get("on_apply_effects")
        return True, final_log, derivative_effects
        
    # ... 其他所有方法保持不变，此处省略 ...
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