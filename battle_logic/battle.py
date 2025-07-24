# battle_logic/battle.py
from __future__ import annotations
import random
import math
from collections import deque
from typing import List, Optional, Dict, Any, Literal, Type, Hashable

from .pokemon import Pokemon, Move
from .constants import BattleState, TypeEffectiveness, Stat, MoveCategory
from .factory import GameDataFactory
from .components import VolatileFlagComponent, StatusEffectComponent, CriticalBoostComponent
from astrbot.api import logger

Action = Dict[Literal["type", "pokemon", "data", "priority"], Any]

class Battle:
    def __init__(self, player_team: List[Pokemon], npc_team: List[Pokemon], factory: GameDataFactory):
        self.player_team: List[Pokemon] = player_team
        self.npc_team: List[Pokemon] = npc_team
        self.factory: GameDataFactory = factory
        self.player_active_pokemon: Optional[Pokemon] = player_team[0] if player_team else None
        self.npc_active_pokemon: Optional[Pokemon] = npc_team[0] if npc_team else None
        self.turn_count: int = 0
        self.state: BattleState = BattleState.FIGHTING
        self.action_history: Dict[Hashable, deque] = {}
        self.history_limit: int = 5
        from .effects import EFFECT_HANDLER_MAP, BaseEffect
        self.effect_handler_classes: Dict[str, Type[BaseEffect]] = EFFECT_HANDLER_MAP

    def process_turn(self, player_action_intent: Dict) -> Dict[str, Any]:
        log = []
        player, npc = self.player_active_pokemon, self.npc_active_pokemon

        try:
            self.turn_count += 1
            log.append(f"--- 第 {self.turn_count} 回合 ---")
            if not player or not npc:
                return self._build_turn_result(log)

            player_action = self._create_action_from_intent(player, player_action_intent)
            npc_action = self._create_npc_action(npc)

            action_order = sorted(
                [player_action, npc_action],
                key=lambda x: (x['priority'], x['pokemon'].get_modified_stat(Stat.SPEED)),
                reverse=True
            )

            for action in action_order:
                actor = action['pokemon']
                opponent = self.npc_active_pokemon if actor is self.player_active_pokemon else self.player_active_pokemon

                if actor.is_fainted() or not opponent:
                    continue

                self._execute_action_core(actor, opponent, action, log)
                if self._handle_fainting_and_state_update(log) or self.is_over(): break
                
                self._process_post_action_triggers(actor, log)
                if self._handle_fainting_and_state_update(log) or self.is_over(): break

                self._resolve_end_of_turn_effects(opponent, log)
                if self._handle_fainting_and_state_update(log) or self.is_over(): break
            
            if not self.is_over() and self.state != BattleState.AWAITING_SWITCH:
                self.state = BattleState.FIGHTING
            
            return self._build_turn_result(log)

        finally:
            if player: player.clear_turn_effects()
            if npc: npc.clear_turn_effects()

    def _process_post_action_triggers(self, actor: Pokemon, log: list):
        active_sequences = actor.get_effects_by_category("sequence")
        if not active_sequences: return

        action_history = self.get_action_history_for(actor)
        move_this_turn = action_history[0] if action_history else None

        sorted_sequences = sorted(active_sequences, key=lambda eff: eff.data.get("source_slot_index", 99))
        
        for sequence in sorted_sequences:
            if move_this_turn and sequence.source_move == move_this_turn.name:
                continue
            
            opponent = self.npc_active_pokemon if actor in self.player_team else self.player_active_pokemon
            if not opponent or opponent.is_fainted():
                return

            sequence_id, charges = sequence.data.get("sequence_id"), sequence.data.get("charges", 0)
            if not sequence_id or charges <= 0: continue
            
            steps = self.factory.get_follow_up_sequence(sequence_id)
            if not steps:
                actor.remove_effect(sequence.effect_id); continue
            
            total_charges = sequence.data.get("total_charges", len(steps))
            step_index = total_charges - charges
            
            if step_index < len(steps):
                log.append(f"  由 [{sequence.source_move or '序列'}] 追击 - 第 {step_index + 1}/{total_charges} 段：")
                move = Move(name="追击效果", display={}, on_use={})
                
                self.execute_effect_list(steps[step_index], actor, opponent, move, log)
                
                sequence.data["charges"] -= 1
                if sequence.data["charges"] <= 0:
                    actor.remove_effect(sequence.effect_id)
                    log.append(f"  {self._get_pokemon_log_prefix(actor)}{actor.name} 的 [{sequence.source_move}] 序列结束了。")
                
                if opponent.is_fainted():
                    break

    def execute_effect_list(self, effect_list: List[Dict], attacker: Pokemon, defender: Pokemon, move: Move, log: list):
        if not effect_list: return
        for effect_data in effect_list:
            handler_class = self.effect_handler_classes.get(effect_data.get("handler"))
            if handler_class and random.random() <= effect_data.get("chance", 100) / 100.0:
                handler_class(self, effect_data).execute(attacker, defender, move, log)

    def _build_turn_result(self, log: List[str]) -> Dict[str, Any]:
        return {"log": "\n".join(log), "state": self.state, "is_over": self.is_over(), "winner": self.get_winner()}

    def _execute_action_core(self, actor: Pokemon, opponent: Optional[Pokemon], action: Action, log: list):
        if action["type"] == "immobilized_turn":
            log.append(f"{self._get_pokemon_log_prefix(actor)}{actor.name} 无法行动！")
            return
        if self._check_can_act(actor, log):
            if action["type"] == "attack":
                move_used = action["data"]
                self._record_action(actor, move_used)
                if move_used.max_pp is not None:
                    actor.use_move(move_used.name)
                self._perform_action_attack(actor, opponent, move_used, log)
            elif action["type"] == "switch":
                self._perform_action_switch(actor, action["data"], log)

    def _handle_fainting_and_state_update(self, log: list) -> bool:
        player_fainted = self.player_active_pokemon and self.player_active_pokemon.is_fainted()
        npc_fainted = self.npc_active_pokemon and self.npc_active_pokemon.is_fainted()

        if not player_fainted and not npc_fainted:
            return False

        if player_fainted:
            if self.state != BattleState.AWAITING_SWITCH and self.state != BattleState.ENDED:
                log.append(f"  {self._get_pokemon_log_prefix(self.player_active_pokemon)}{self.player_active_pokemon.name} 倒下了！")
            
            if self.get_player_survivors():
                self.state = BattleState.AWAITING_SWITCH
            else:
                self.state = BattleState.ENDED
            return True

        if npc_fainted:
            faint_msg = f"{self.npc_active_pokemon.name} 倒下了！"
            if not any(faint_msg in line for line in log[-3:]):
                 log.append(f"  {self._get_pokemon_log_prefix(self.npc_active_pokemon)}{faint_msg}")

            next_npc = self.get_next_npc_pokemon()
            if next_npc:
                self.npc_active_pokemon = next_npc
                log.append(f"(NPC) 派出了新的宝可梦：{next_npc.name}！")
            else:
                self.state = BattleState.ENDED
            return True
        return False

    def process_faint_switch(self, new_pokemon: Pokemon) -> Dict[str, Any]:
        if self.state != BattleState.AWAITING_SWITCH: return {"success": False, "log": "错误：当前不处于等待换人状态。"}
        if new_pokemon.is_fainted() or new_pokemon not in self.player_team: return {"success": False, "log": "错误：选择的宝可梦无效或已倒下。"}
        p_out = self.player_active_pokemon
        if p_out: p_out.on_switch_out(); self._clear_history_for(p_out)
        self.player_active_pokemon = new_pokemon; self.state = BattleState.FIGHTING
        return {"success": True, "log": f"去吧，{new_pokemon.name}！"}

    def _check_critical_hit(self, attacker: Pokemon) -> bool:
        base_crit_chance = 0.0525 + (attacker.crit_points * 0.0005)
        crit_multiplier = 2.0 if attacker.aura.get_components(CriticalBoostComponent) else 1.0
        return random.random() < min(base_crit_chance * crit_multiplier, 1.0)

    def _check_can_act(self, pokemon: Pokemon, log: list) -> bool:
        prefix = self._get_pokemon_log_prefix(pokemon)
        if any(c.flag_id == 'flinch' for c in pokemon.aura.get_components(VolatileFlagComponent)):
            log.append(f"{prefix}{pokemon.name} 畏缩了，无法行动！"); return False
        for effect_comp in pokemon.aura.get_components(StatusEffectComponent):
            if effect_comp.effect_id == "paralysis":
                if random.random() < effect_comp.properties.get("immobility_chance", 0.25):
                    log.append(f"{prefix}{pokemon.name} 全身麻痹，无法行动！"); return False
        return True

    def _resolve_end_of_turn_effects(self, pokemon: Pokemon, log: list):
        if pokemon.is_fainted(): return
        for effect_comp in list(pokemon.aura.get_components(StatusEffectComponent)):
            if pokemon.is_fainted(): break
            # 修正：状态激活日志不应在此处生成，此处仅负责倒计时
            if effect_comp.effect_id == "immobilized" and "delay_activation_turns" in effect_comp.data:
                effect_comp.data["delay_activation_turns"] -= 1
                continue # 倒计时后继续处理其他效果
            props = effect_comp.properties
            if 'damage_per_turn' in props:
                damage = max(1, math.floor(pokemon.max_hp * props["damage_per_turn"]))
                pokemon.take_damage(damage, source_move=effect_comp.name)
                log.append(f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 因 [{effect_comp.name}] 受到了 {damage} 点伤害！")
            if 'duration' in effect_comp.data and effect_comp.data['duration'] > 0:
                effect_comp.data['duration'] -= 1
                if effect_comp.data['duration'] <= 0:
                    log.append(f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 的 [{effect_comp.name}] 效果结束了。")
                    pokemon.aura.remove_component(effect_comp)
            elif 'clear_chance' in props and random.random() < props['clear_chance']:
                 log.append(f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 从 [{effect_comp.name}] 中恢复了！")
                 pokemon.aura.remove_component(effect_comp)

    def _perform_action_attack(self, attacker: Pokemon, opponent: Optional[Pokemon], move: Move, log: list):
        log.append(f"{self._get_pokemon_log_prefix(attacker)}{attacker.name} 使用了 {move.name}！")
        if not opponent: log.append("  但是没有目标！"); return
        if self._check_hit(attacker, opponent, move):
            self.execute_effect_list(move.effects, attacker, opponent, move, log)
        else: log.append("  但攻击落空了！")

    def _perform_action_switch(self, p_out: Pokemon, p_in: Pokemon, log: list):
        log.append(f"{self._get_pokemon_log_prefix(p_out)}收回了 {p_out.name}！"); p_out.on_switch_out(); self._clear_history_for(p_out)
        if p_out in self.player_team: self.player_active_pokemon = p_in
        else: self.npc_active_pokemon = p_in
        log.append(f"{self._get_pokemon_log_prefix(p_in)}去吧，{p_in.name}！")

    def calculate_damage(self, attacker: Pokemon, defender: Pokemon, move: Move) -> Dict[str, Any]:
        result = {"damage": 0, "log_msg": "", "is_crit": False};
        if move.category == MoveCategory.STATUS: return result
        effectiveness = TypeEffectiveness.get_effectiveness(move.type, defender.types, self.factory.get_type_chart())
        if effectiveness == 0:
            result["log_msg"] = f"这对 {self._get_pokemon_log_prefix(defender)}{defender.name} 没有任何效果！"; return result
        attack_stat = attacker.get_modified_stat(Stat.ATTACK if move.category == MoveCategory.PHYSICAL else Stat.SPECIAL_ATTACK)
        defense_stat = defender.get_modified_stat(Stat.DEFENSE if move.category == MoveCategory.PHYSICAL else Stat.SPECIAL_DEFENSE)
        damage = (((2 * attacker.level / 5 + 2) * move.display_power * attack_stat / defense_stat) / 50) + 2
        if self._check_critical_hit(attacker): damage *= 2.0; result["is_crit"] = True; result["log_msg"] += "击中了要害！"
        damage *= random.uniform(0.85, 1.0)
        if move.type in attacker.types: damage *= 1.5
        damage *= effectiveness
        if effectiveness > 1: result["log_msg"] += " 效果绝佳！"
        elif effectiveness < 1: result["log_msg"] += " 效果不理想..."
        result["damage"] = math.floor(max(1, damage)); result["log_msg"] = result["log_msg"].strip()
        return result


    def _check_hit(self, attacker: Pokemon, defender: Pokemon, move: Move) -> bool:
        """
        根据精确的优先级顺序，判断技能是否命中。
        优先级顺序:
        1. 必中技能判定 (最高优先级)
        2. 闪避状态判定
        3. 基础命中率判定 (最低优先级)
        """
        # 规则 1: 检查技能是否为“必中技能”。如果是，则无视一切条件，直接命中。
        if move.guaranteed_hit:
            return True

        # 规则 2: 检查防御方是否处于“闪避状态”。如果是，则无视命中率，直接落空。
        # (此检查仅在技能不是必中技能时才会执行)
        for effect in defender.aura.get_components(StatusEffectComponent):
            if effect.properties.get("guaranteed_evasion"):
                return False

        # 规则 3: 如果以上条件都不满足，则根据技能的基础命中率进行随机判定。
        # (accuracy 为 None 或 100 时，等同于必定命中)
        if move.accuracy is None:
            return True
        return random.randint(1, 100) <= move.accuracy


    def _create_action_from_intent(self, pokemon: Pokemon, intent: Dict) -> Action:
        # 在回合开始创建意图时，最优先检查是否处于无法行动状态。
        immobilized = pokemon.get_effect("immobilized")
        if immobilized and immobilized.data.get("delay_activation_turns", 0) <= 0:
            return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}
            
        if intent.get("type") == "force_immobilized_turn":
            return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}

        if not pokemon.has_usable_moves() and intent.get("type") != "switch":
            return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}
            
        action_type = intent.get("type")
        if action_type == "attack":
            move = intent.get("data");
            if move: return {"type": "attack", "pokemon": pokemon, "data": move, "priority": move.priority}
        elif action_type == "switch":
            target = intent.get("data");
            if target: return {"type": "switch", "pokemon": pokemon, "data": target, "priority": 8}
            
        logger.warning(f"宝可梦 {pokemon.name} 收到无效行动意图 ({intent.get('type')})，强制进入无法行动。")
        return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}

    def _create_npc_action(self, pokemon: Pokemon) -> Action:
        # 在回合开始创建意图时，最优先检查是否处于无法行动状态。
        immobilized = pokemon.get_effect("immobilized")
        if immobilized and immobilized.data.get("delay_activation_turns", 0) <= 0:
            return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}

        if not pokemon.has_usable_moves():
            return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}
            
        usable = [s.move for s in pokemon.skill_slots if s.move.max_pp is None or pokemon.get_current_pp(s.move.name) > 0]
        if usable:
            move = random.choice(usable)
            return {"type": "attack", "pokemon": pokemon, "data": move, "priority": move.priority}
            
        logger.error(f"NPC宝可梦 {pokemon.name} 逻辑错误：未能选择技能，强制进入无法行动。")
        return {"type": "immobilized_turn", "pokemon": pokemon, "data": None, "priority": 8}
    
    def is_over(self) -> bool: return all(p.is_fainted() for p in self.player_team) or all(p.is_fainted() for p in self.npc_team)

    def get_winner(self) -> Optional[str]:
        if not self.is_over(): return None
        return "Player" if all(p.is_fainted() for p in self.npc_team) else "NPC"

    def _get_pokemon_log_prefix(self, p: Pokemon) -> str: return "(玩家)" if p in self.player_team else "(NPC)"

    def get_player_survivors(self) -> List[Pokemon]: return [p for p in self.player_team if not p.is_fainted()]

    def get_next_npc_pokemon(self) -> Optional[Pokemon]: return next((p for p in self.npc_team if not p.is_fainted()), None)

    def get_action_history_for(self, pokemon: Pokemon) -> List[Move]: return list(reversed(self.action_history.get(id(pokemon), deque())))

    def _record_action(self, pokemon: Pokemon, move: Move):
        pid = id(pokemon)
        if move and move.name != "追击效果":
            if pid not in self.action_history: self.action_history[pid] = deque(maxlen=self.history_limit)
            self.action_history[pid].append(move)

    def _clear_history_for(self, pokemon: Pokemon):
        if id(pokemon) in self.action_history: del self.action_history[id(pokemon)]