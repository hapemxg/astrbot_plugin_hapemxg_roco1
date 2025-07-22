# battle_logic/pokemon.py
import math
import random
from typing import Dict, List, Optional, Tuple, Any, NamedTuple, TYPE_CHECKING
from .move import Move
from .constants import Stat, EFFECT_PROPERTIES, STAT_NAME_MAP

if TYPE_CHECKING: from .factory import GameDataFactory

class SkillSlot(NamedTuple):
    index: int
    move: Move

class AppliedEffect:
    """代表一个已施加在宝可梦身上的具体效果实例。"""
    def __init__(self, effect_id: str, source_move: Optional[str] = None):
        properties = EFFECT_PROPERTIES.get(effect_id)
        # 如果是动态生成的序列ID，则动态获取属性
        if not properties and effect_id.startswith("sequence_slot_"):
            properties = {"category": "sequence"}

        self.id = effect_id
        self.name = properties.get('name', effect_id)
        self.is_volatile = properties.get('is_volatile', False)
        self.source_move = source_move
        self.data: Dict[str, Any] = {}
        
        if properties and 'max_duration' in properties:
            # 确保最小持续时间至少为1
            min_duration = max(1, properties.get('min_duration', properties['max_duration'] - 2))
            self.data['duration'] = random.randint(min_duration, properties['max_duration'])

class Pokemon:
    def __init__(self, name: str, level: int, types: List[str], stats: Dict[str, int], move_names: List[str], factory: 'GameDataFactory'):
        self.name = name; self.level = level; self.types = types
        self.crit_points = stats.get("crit_points", 0); self.base_stats = stats
        self.stats = self._calculate_stats(self.base_stats, self.level)
        self.max_hp = self.stats.get(Stat.HP, 1); self.current_hp = self.max_hp
        self.skill_slots: List[SkillSlot] = []; self._initialize_moves(move_names, factory)
        
        self.effects: List[AppliedEffect] = []
        self.stat_stages: Dict[Stat, int] = {stat: 0 for stat in Stat if stat != Stat.HP}
        self.crit_rate_stage: int = 0

    def _calculate_stats(self, base_stats: Dict[str, int], level: int) -> Dict[Stat, int]:
        IV, EV_TERM = 31, 0; final_stats = {}
        final_stats[Stat.HP] = math.floor(((2 * base_stats.get("hp", 1) + IV + EV_TERM) * level) / 100) + level + 10
        other_stats = {"attack": Stat.ATTACK, "defense": Stat.DEFENSE, "special_attack": Stat.SPECIAL_ATTACK, "special_defense": Stat.SPECIAL_DEFENSE, "speed": Stat.SPEED}
        for key, stat in other_stats.items(): final_stats[stat] = math.floor((((2 * base_stats.get(key, 1) + IV + EV_TERM) * level) / 100) + 5)
        return final_stats

    def _initialize_moves(self, move_names: List[str], factory: 'GameDataFactory'):
        from astrbot.api import logger; from copy import deepcopy
        for i, name in enumerate(move_names):
            template = factory.get_move_template(name)
            if template: self.skill_slots.append(SkillSlot(index=i, move=deepcopy(template)))
            else: logger.warning(f"未能为 {self.name} 加载技能 '{name}'。")

    @property
    def moves(self) -> Dict[str, Move]: return {s.move.name: s.move for s in self.skill_slots}
    def is_fainted(self) -> bool: return self.current_hp <= 0
    def take_damage(self, dmg: int): self.current_hp = max(0, self.current_hp - dmg)
    def heal(self, amt: int): self.current_hp = min(self.max_hp, self.current_hp + amt)
    def get_move_by_name(self, name: str) -> Optional[Move]: return next((s.move for s in self.skill_slots if s.move.name == name), None)
    def use_move(self, name: str):
        move = self.get_move_by_name(name)
        if move and move.name != "挣扎" and move.current_pp is not None and move.current_pp > 0: move.current_pp -= 1
    def has_usable_moves(self) -> bool:
        return any(slot.move.current_pp is None or slot.move.current_pp > 0 for slot in self.skill_slots)

    def has_effect(self, effect_id: str) -> bool:
        return any(eff.id == effect_id for eff in self.effects)

    def get_effect(self, effect_id: str) -> Optional[AppliedEffect]:
        return next((eff for eff in self.effects if eff.id == effect_id), None)

    def get_effects_by_category(self, category: str) -> List[AppliedEffect]:
        """获取宝可梦身上所有属于指定类别的效果。"""
        return [eff for eff in self.effects if self._get_effect_props(eff.id).get('category') == category]

    def _get_effect_props(self, effect_id: str) -> Dict:
        """内部辅助方法，用于动态获取序列效果的属性。"""
        props = EFFECT_PROPERTIES.get(effect_id)
        if not props and effect_id.startswith("sequence_slot_"):
            return {"category": "sequence", "stacking_behavior": "refresh"}
        return props or {}

    def apply_effect(self, effect_id: str, source_move: Optional[str] = None, options: Optional[Dict] = None) -> Tuple[bool, str, Optional[List[Dict]]]:
        """
        【重构】施加效果，并返回是否成功、日志消息以及任何需要立即执行的衍生效果。
        
        Returns:
            A tuple of (success, message, derivative_effects).
        """
        new_props = self._get_effect_props(effect_id)
        derivative_effects = None  # 初始化衍生效果列表
        
        # --- 步骤1: 预处理和冲突检测 ---
        existing_effect = self.get_effect(effect_id)
        if existing_effect:
            if new_props.get("stacking_behavior", "ignore") == "ignore":
                return False, f"{self.name} 已经处于 [{existing_effect.name}] 状态。", None
        
        effect_to_replace = None
        if new_props.get('category') == 'status':
            new_status_type = new_props.get('status_type')
            if new_status_type:
                for eff in self.effects:
                    eff_props = self._get_effect_props(eff.id)
                    if eff_props.get('status_type') == new_status_type:
                        effect_to_replace = eff
                        break
        
        # --- 步骤2: 执行操作 (移除旧的，添加新的) ---
        if existing_effect and new_props.get("stacking_behavior") == "refresh":
            self.remove_effect(effect_id)
        if effect_to_replace:
            self.remove_effect(effect_to_replace.id)
            
        new_effect = AppliedEffect(effect_id, source_move)
        if options: new_effect.data.update(options)
        self.effects.append(new_effect)

        # 【修复】检查并设置衍生效果
        if new_props.get("on_apply_effects"):
            derivative_effects = new_props["on_apply_effects"]

        # --- 步骤3: 生成日志报告 ---
        effect_name = new_props.get("name", effect_id)
        if effect_to_replace:
            return True, f"的 [{effect_name}] 效果替换了 [{effect_to_replace.name}]！", derivative_effects
        elif new_props.get('category') == 'status':
            return True, f"陷入了 [{effect_name}] 状态！", derivative_effects
        else:
            return True, f"获得了 [{effect_name}] 效果！", derivative_effects

    def remove_effect(self, effect_id: str) -> bool:
        initial_len = len(self.effects)
        self.effects = [eff for eff in self.effects if eff.id != effect_id]
        return len(self.effects) < initial_len

    def on_switch_out(self):
        self.effects = [effect for effect in self.effects if not effect.is_volatile]

    def clear_turn_effects(self):
        """清除所有生命周期为'turn'的效果，并移除序列效果的'is_activation_turn'标记。"""
        self.effects = [eff for eff in self.effects if self._get_effect_props(eff.id).get('lifespan') != 'turn']
        for eff in self.effects:
            if eff.id.startswith("sequence_slot_") and "is_activation_turn" in eff.data:
                del eff.data["is_activation_turn"]

    def get_modified_stat(self, stat: Stat) -> int:
        base = self.stats.get(stat, 1)
        stage = self.stat_stages.get(stat, 0)
        mult = (2 + abs(stage)) / 2 if stage > 0 else 2 / (2 + abs(stage))
        modified = math.floor(base * mult)
        for effect in self.effects:
            props = self._get_effect_props(effect.id)
            if stat in props.get("stat_modifiers", {}):
                modified *= props["stat_modifiers"][stat]
        return math.floor(modified)

    def apply_stat_change(self, stat: Stat, stages: int) -> Tuple[bool, str]:
        current = self.stat_stages.get(stat, 0); new = max(-6, min(6, current + stages))
        if new == current: return False, f"{self.name} 的{STAT_NAME_MAP.get(stat)}已无法再{'提升' if stages > 0 else '降低'}！"
        self.stat_stages[stat] = new
        msg = f"{self.name} 的{STAT_NAME_MAP.get(stat)}";
        if abs(stages) >= 2: msg += "大幅"
        msg += "提升了！" if stages > 0 else "降低了！"
        return True, msg

    def change_crit_stage(self, stages: int) -> Tuple[bool, str]:
        current = self.crit_rate_stage; new = max(0, min(3, current + stages))
        if new == current: return False, f"{self.name} 的要害攻击率已无法再提升！"
        self.crit_rate_stage = new
        return True, f"{self.name} 更容易击中要害了！"