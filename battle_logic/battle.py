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
        """
        【已重构】处理一个完整的大回合，包含两个小回合。
        """
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

            # --- 核心回合流程 ---
            for i, action in enumerate(action_order):
                # 确定当前小回合的行动方和被动方
                actor = action['pokemon']
                # 【关键】被动方是另一只在场上的宝可梦
                passive_target = self.npc_active_pokemon if actor is self.player_active_pokemon else self.player_active_pokemon
                
                if actor.is_fainted() or not passive_target:
                    continue

                # 1. 执行核心动作 (包含混乱、斗转星移等目标反转逻辑)
                self._execute_action_core(actor, passive_target, action, log)
                if self._handle_fainting_and_state_update(log) or self.is_over(): break
                
                # 2. 结算追击效果
                self._process_post_action_triggers(actor, log)
                if self._handle_fainting_and_state_update(log) or self.is_over(): break

                # 3. 【核心修改】结算被动方的回合末效果 (如中毒、寄生等)
                #    我们将当前小回合的行动方(actor)作为治疗目标传入
                self._resolve_end_of_turn_effects(passive_target, actor, log)
                if self._handle_fainting_and_state_update(log) or self.is_over(): break
            
            if not self.is_over() and self.state != BattleState.AWAITING_SWITCH:
                self.state = BattleState.FIGHTING
            
            return self._build_turn_result(log)

        finally:
            if player: player.clear_turn_effects()
            if npc: npc.clear_turn_effects()

    def _execute_action_core(self, actor: Pokemon, opponent: Optional[Pokemon], action: Action, log: list):
        """【已重构】分发动作，并在需要时调用目标反转服务。"""
        if action["type"] == "immobilized_turn":
            log.append(f"{self._get_pokemon_log_prefix(actor)}{actor.name} 无法行动！")
            return
            
        if not self._check_can_act(actor, log):
            return

        if action["type"] == "attack":
            move_used = action["data"]
            target_override = None

            # --- 目标反转机制检查点 ---
            # 1. 混乱检查
            if actor.has_effect("confusion") and random.random() < 0.50:
                log.append(f"{self._get_pokemon_log_prefix(actor)}{actor.name} 陷入了混乱！它攻击了自己！")
                target_override = actor
                # TODO: 在此处理50%概率解除混乱的逻辑

            # 2. 斗转星移 (反弹) 检查
            elif opponent and opponent.has_effect("reversal_stance"):
                opponent.remove_effect("reversal_stance")
                log.append(f"（斗转星移！）{self._get_pokemon_log_prefix(opponent)}{opponent.name} 将攻击反弹了回去！")
                target_override = actor

            self._execute_action_with_target_override(actor, opponent, move_used, log, target_override)

        elif action["type"] == "switch":
            self._perform_action_switch(actor, action["data"], log)

    def _execute_action_with_target_override(
        self,
        actor: Pokemon,
        original_opponent: Optional[Pokemon],
        move: Move,
        log: list,
        target_override: Optional[Pokemon] = None
    ):
        """【新增】执行攻击的核心服务，允许强制覆盖目标。"""
        self._record_action(actor, move)
        if move.max_pp is not None:
            actor.use_move(move.name)

        final_defender = target_override if target_override is not None else original_opponent
        
        log.append(f"{self._get_pokemon_log_prefix(actor)}{actor.name} 使用了 {move.name}！")
        if not final_defender:
            log.append("  但是没有目标！")
            return

        if self._check_hit(actor, final_defender, move):
            self.execute_effect_list(move.effects, actor, final_defender, move, log)
        else:
            log.append("  但攻击落空了！")
    
    def _check_can_act(self, pokemon: Pokemon, log: list) -> bool:
        """
        【最终精炼版】一个纯粹的、由JSON驱动的“行动前检查”执行引擎。
        """
        prefix = self._get_pokemon_log_prefix(pokemon)
        opponent = self.npc_active_pokemon if pokemon in self.player_team else self.player_active_pokemon

        # 1. 优先处理“畏缩”
        if any(c.flag_id == 'flinch' for c in pokemon.aura.get_components(VolatileFlagComponent)):
            log.append(f"{prefix}{pokemon.name} 畏缩了，无法行动！")
            return False

        # 2. 通用“行动前检查”循环
        for effect_comp in list(pokemon.aura.get_components(StatusEffectComponent)):
            check_props = effect_comp.properties.get("on_pre_action_check")
            if not check_props:
                continue
            
            # A. 【精炼】处理持续时间 和 概率解除
            # 它们现在可以和谐共存
            turns_passed = effect_comp.data.get("pre_action_turns", 0) + 1
            duration = check_props.get("duration")
            
            # 检查是否因达到持续时间上限而强制解除
            if duration is not None and turns_passed > duration:
                log.append(f"  {prefix}{pokemon.name} 的 [{effect_comp.name}] 效果结束了。")
                pokemon.aura.remove_component(effect_comp)
                continue # 已解除，继续检查其他效果

            # 如果没到上限，再检查是否因概率而提前解除
            cleared_this_turn = False
            clear_chances = check_props.get("clear_chances")
            if clear_chances:
                is_first_check = turns_passed == 1
                chance = clear_chances.get("first_turn", 0) if is_first_check else clear_chances.get("subsequent_turns", 0)
                if random.random() < chance:
                    cleared_this_turn = True

            # 更新回合计数器
            effect_comp.data["pre_action_turns"] = turns_passed

            # B. 根据是否解除成功，执行对应的效果列表
            move_for_effect = Move(name=f"[{effect_comp.name}]效果", display={}, on_use={})
            if cleared_this_turn:
                log.append(f"  {prefix}{pokemon.name} 从 [{effect_comp.name}] 中恢复了！")
                effects_to_run = check_props.get("on_clear_success", [])
                self.execute_effect_list(effects_to_run, pokemon, opponent, move_for_effect, log)
                pokemon.aura.remove_component(effect_comp)
                # 【关键】因为此状态已解除，所以我们应该继续检查下一个可能阻止行动的状态
                continue 
            else:
                effects_to_run = check_props.get("on_clear_fail", [])
                self.execute_effect_list(effects_to_run, pokemon, opponent, move_for_effect, log)

            # C. 最终决定是否能行动
            if check_props.get("blocks_action"):
                log.append(f"{prefix}{pokemon.name} 因 [{effect_comp.name}] 而无法行动！")
                return False
        
        # 3. 处理麻痹等其他简单状态
        for effect_comp in pokemon.aura.get_components(StatusEffectComponent):
            if random.random() < effect_comp.properties.get("immobility_chance", 0):
                log.append(f"{prefix}{pokemon.name} 因 [{effect_comp.name}] 而全身麻痹，无法行动！")
                return False

        return True

    def _resolve_end_of_turn_effects(self, target: Pokemon, turn_actor: Pokemon, log: list):
        if target.is_fainted(): return
        
        prefix = self._get_pokemon_log_prefix(target)
        for effect_comp in list(target.aura.get_components(StatusEffectComponent)):
            if target.is_fainted(): break
            
            props = effect_comp.properties
            
            # 【新增】通用回合末持续时间处理 (for 寄生, 束缚等)
            if 'duration' in props:
                # 首次结算时，在组件data中初始化计数器
                turns_passed = effect_comp.data.get("end_of_turn_counter", 0) + 1
                if turns_passed > props['duration']:
                    log.append(f"  {prefix}{target.name} 的 [{effect_comp.name}] 效果结束了。")
                    target.aura.remove_component(effect_comp)
                    continue # 效果已结束，检查下一个
                effect_comp.data["end_of_turn_counter"] = turns_passed
            
            # --- 剧毒 (Toxic) 的特殊伤害逻辑 ---
            if props.get("ramping_damage"):
                counter = effect_comp.data.get("toxic_counter", 1)
                damage = max(1, math.floor(target.max_hp * 0.0625 * counter))
                damage = min(damage, 500) # 伤害上限
                
                target.take_damage(damage, source_move=effect_comp.name)
                log.append(f"  {self._get_pokemon_log_prefix(target)}{target.name} 因 [{effect_comp.name}] 受到了 {damage} 点伤害！ (计数: {counter})")
                effect_comp.data["toxic_counter"] = counter + 1
                continue # 跳过通用处理

            # --- 寄生 (Leech Seed) 的特殊治疗逻辑 ---
            if props.get("heals_opponent"):
                damage = max(1, math.floor(target.max_hp * props.get("damage_per_turn", 0)))
                target.take_damage(damage, source_move=effect_comp.name)
                log.append(f"  {self._get_pokemon_log_prefix(target)}{target.name} 的养分被吸取了！ (损失 {damage} HP)")

                # 治疗当前小回合的行动方 (turn_actor)
                if turn_actor and not turn_actor.is_fainted():
                    turn_actor.heal(damage, source_move=effect_comp.name)
                    log.append(f"  {self._get_pokemon_log_prefix(turn_actor)}{turn_actor.name} 回复了精力！ (回复 {damage} HP)")
                continue

            # --- 通用伤害逻辑 (如烧伤、普通中毒) ---
            if 'damage_per_turn' in props:
                damage = max(1, math.floor(target.max_hp * props["damage_per_turn"]))
                target.take_damage(damage, source_move=effect_comp.name)
                log.append(f"  {self._get_pokemon_log_prefix(target)}{target.name} 因 [{effect_comp.name}] 受到了 {damage} 点伤害！")

            # --- 通用效果持续时间/解除逻辑 ---
            if 'duration' in effect_comp.data and effect_comp.data['duration'] > 0:
                effect_comp.data['duration'] -= 1
                if effect_comp.data['duration'] <= 0:
                    log.append(f"  {self._get_pokemon_log_prefix(target)}{target.name} 的 [{effect_comp.name}] 效果结束了。")
                    target.aura.remove_component(effect_comp)

    # --- 以下方法大多保持不变，仅为保持完整性而提供 ---
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

    def _check_critical_hit(self, attacker: Pokemon) -> bool:
        base_crit_chance = 0.0525 + (attacker.crit_points * 0.0005)
        crit_multiplier = 2.0 if attacker.aura.get_components(CriticalBoostComponent) else 1.0
        return random.random() < min(base_crit_chance * crit_multiplier, 1.0)
        
    def _check_hit(self, attacker: Pokemon, defender: Pokemon, move: Move) -> bool:
        if move.guaranteed_hit:
            return True
        if any(effect.properties.get("guaranteed_evasion") for effect in defender.aura.get_components(StatusEffectComponent)):
            return False
        if move.accuracy is None:
            return True
        return random.randint(1, 100) <= move.accuracy

    def _create_action_from_intent(self, pokemon: Pokemon, intent: Dict) -> Action:
        immobilized_effect = pokemon.get_effect("immobilized")
        if immobilized_effect and not immobilized_effect.data.get('is_newly_applied', False):
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