# battle_logic/battle.py
import random
import math
from collections import deque
from typing import List, Optional, Dict, Any, Literal, Type, Hashable
from copy import deepcopy

from .pokemon import Pokemon, Move
from .constants import BattleState, TypeEffectiveness, EFFECT_PROPERTIES, Stat, MoveCategory
from .factory import GameDataFactory

# 类型别名，用于清晰地表示行动意图
Action = Dict[Literal["type", "pokemon", "data", "priority"], Any]

class Battle:
    """
    封装了宝可梦对战的核心逻辑。

    该类采用了“小回合”结算模型和“可查询历史记录”模式，以确保行动时序的精确性、
    状态结算的原子性，以及架构的高度模块化和可扩展性。
    """
    def __init__(self, player_team: List[Pokemon], npc_team: List[Pokemon], factory: GameDataFactory):
        """
        初始化一场新的战斗。

        Args:
            player_team: 玩家的宝可梦队伍列表。
            npc_team: NPC的宝可梦队伍列表。
            factory: 用于创建游戏数据的 GameDataFactory 实例。
        """
        self.player_team: List[Pokemon] = player_team
        self.npc_team: List[Pokemon] = npc_team
        self.factory: GameDataFactory = factory
        
        self.player_active_pokemon: Optional[Pokemon] = player_team[0] if player_team else None
        self.npc_active_pokemon: Optional[Pokemon] = npc_team[0] if npc_team else None
        
        self.turn_count: int = 0
        self.state: BattleState = BattleState.FIGHTING
        
        # 【终极架构】一个真正的、有固定长度限制的历史记录系统。
        self.action_history: Dict[Hashable, deque] = {}
        self.history_limit: int = 5  # 最近5回合的记录

        # 动态导入效果处理器，避免循环依赖
        from .effects import EFFECT_HANDLER_MAP, BaseEffect
        self.effect_handler_classes: Dict[str, Type[BaseEffect]] = EFFECT_HANDLER_MAP
        
        # 初始化“挣扎”技能模板
        self.struggle_move_template: Move = self._initialize_struggle_move()

    def _initialize_struggle_move(self) -> Move:
        """加载或创建“挣扎”技能的备用模板。"""
        struggle = self.factory.get_move_template("挣扎")
        if struggle: return struggle
        
        from astrbot.api import logger
        logger.warning("未能从 moves.json 加载“挣扎”技能，将使用内置的默认版本。")

        # 因为没有技能可以使用了，只能原地罚站，不会造成任何效果。
        default_display = {"power": 0, "pp": None, "type": "一般", "category": "status"}
        default_on_use = {
            "priority": 0, 
            "guaranteed_hit": True, 
            "effects": []
        }
        return Move(name="挣扎", display=default_display, on_use=default_on_use)

    # --- 辅助方法 ---
    def is_over(self) -> bool:
        return all(p.is_fainted() for p in self.player_team) or all(p.is_fainted() for p in self.npc_team)

    def get_winner(self) -> Optional[str]:
        if not self.is_over(): return None
        return "Player" if all(p.is_fainted() for p in self.npc_team) else "NPC"

    def _get_pokemon_log_prefix(self, p: Pokemon) -> str:
        return "(玩家)" if p in self.player_team else "(NPC)"
    
    def get_next_npc_pokemon(self) -> Optional[Pokemon]:
        return next((p for p in self.npc_team if not p.is_fainted()), None)

    # --- 历史记录系统 ---
    def get_action_history_for(self, pokemon: Pokemon) -> List[Move]:
        """以列表形式，返回一个宝可梦的近期行动历史（从最近到最远）。"""
        history_deque = self.action_history.get(id(pokemon))
        if not history_deque: return []
        return list(reversed(history_deque))

    def _record_action(self, pokemon: Pokemon, move: Move):
        """将一次行动记录到对应宝可梦的历史队列中。"""
        pokemon_id = id(pokemon)
        if pokemon_id not in self.action_history:
            self.action_history[pokemon_id] = deque(maxlen=self.history_limit)
        self.action_history[pokemon_id].append(move)

    def _clear_history_for(self, pokemon: Pokemon):
        """当宝可梦切换下场时，清空其历史记录。"""
        pokemon_id = id(pokemon)
        if pokemon_id in self.action_history:
            del self.action_history[pokemon_id]

    # --- 核心回合流程控制 ---
    def process_turn(self, player_action_intent: Dict) -> Dict[str, Any]:
        """主回合处理方法，编排整个回合的流程。"""
        self.turn_count += 1
        log = [f"--- 第 {self.turn_count} 回合 ---"]
        
        player, npc = self.player_active_pokemon, self.npc_active_pokemon
        if not player or not npc:
            return {"log": "错误：一方或双方没有宝可梦在场。", "state": BattleState.ENDED}

        player_action = self._create_action_from_intent(player, player_action_intent)
        npc_action = self._create_npc_action(npc)
        
        action_order = sorted([player_action, npc_action], key=lambda x: (x['priority'], x['pokemon'].get_modified_stat(Stat.SPEED)), reverse=True)
        first_action, second_action = action_order[0], action_order[1]

        if not first_action['pokemon'].is_fainted():
            self._execute_sub_turn(first_action['pokemon'], second_action['pokemon'], first_action, log)

        if self.npc_active_pokemon and self.npc_active_pokemon.is_fainted() and not self.is_over():
            next_npc = self.get_next_npc_pokemon()
            if next_npc:
                self.npc_active_pokemon = next_npc
                log.append(f"(NPC) 派出了 {next_npc.name}！")
        
        if not second_action['pokemon'].is_fainted():
            current_opponent = self.npc_active_pokemon if second_action['pokemon'] == self.player_active_pokemon else self.player_active_pokemon
            if current_opponent and not current_opponent.is_fainted():
                self._execute_sub_turn(second_action['pokemon'], current_opponent, second_action, log)

        if self.player_active_pokemon: self.player_active_pokemon.clear_turn_effects()
        if self.npc_active_pokemon: self.npc_active_pokemon.clear_turn_effects()
        
        if self.player_active_pokemon and self.player_active_pokemon.is_fainted() and not self.is_over():
            self.state = BattleState.AWAITING_SWITCH
            
        return {"log": "\n".join(log), "state": self.state, "is_over": self.is_over(), "winner": self.get_winner()}

    def _execute_sub_turn(self, actor: Pokemon, opponent: Pokemon, action: Action, log: list):
        """执行一个完整的小回合：行动前检查 -> 执行行动 -> 追击 -> 结算对手状态。"""
        if not self._check_can_act(actor, log):
            self._resolve_status_consequences(actor, log)
            return

        if action["type"] == "attack":
            move_used = action["data"]
            self._record_action(actor, move_used) # 记录到历史
            actor.use_move(move_used.name) # 消耗PP
            self._perform_action_attack(actor, opponent, move_used, log)
        elif action["type"] == "switch":
            self._perform_action_switch(actor, action["data"], log)
        
        current_opponent = self.npc_active_pokemon if actor == self.player_active_pokemon else self.player_active_pokemon
        if not current_opponent or current_opponent.is_fainted(): return
        
        self._process_post_action_triggers(actor, current_opponent, log)
        if current_opponent.is_fainted(): return

        self._resolve_status_consequences(current_opponent, log)

    def _create_action_from_intent(self, pokemon: Pokemon, intent: Dict) -> Action:
        action_type = intent.get("type")
        if action_type == "attack":
            move = intent.get("data")
            if move: return {"type": "attack", "pokemon": pokemon, "data": move, "priority": move.priority}
        if action_type == "switch":
            target_pokemon = intent.get("data")
            if target_pokemon: return {"type": "switch", "pokemon": pokemon, "data": target_pokemon, "priority": 8}
        return {"type": "attack", "pokemon": pokemon, "data": self.struggle_move_template, "priority": 0}

    def _create_npc_action(self, pokemon: Pokemon) -> Action:
        if pokemon.has_usable_moves():
            usable_moves = [m for m in pokemon.moves.values() if m.current_pp is None or m.current_pp > 0]
            if usable_moves:
                move = random.choice(usable_moves)
                return {"type": "attack", "pokemon": pokemon, "data": move, "priority": move.priority}
        return {"type": "attack", "pokemon": pokemon, "data": self.struggle_move_template, "priority": 0}

    def _check_can_act(self, pokemon: Pokemon, log: list) -> bool:
        prefix = self._get_pokemon_log_prefix(pokemon)
        if pokemon.has_effect("flinch"):
            log.append(f"{prefix}{pokemon.name} 畏缩了，无法行动！"); return False
        for effect in list(pokemon.effects):
            props = EFFECT_PROPERTIES.get(effect.id, {})
            if props.get("blocks_action"):
                log.append(f"{prefix}{pokemon.name} 因 [{effect.name}] 而无法行动！"); return False
            if effect.id == "paralysis" and random.random() < props.get("immobility_chance", 0.25):
                log.append(f"{prefix}{pokemon.name} 全身麻痹，无法行动！"); return False
        return True

    def _resolve_status_consequences(self, pokemon: Pokemon, log: list):
        if pokemon.is_fainted(): return
        effects_to_remove = []
        for effect in list(pokemon.effects):
            props = EFFECT_PROPERTIES.get(effect.id, {})
            if 'damage_per_turn' not in props and 'duration' not in effect.data and 'clear_chance' not in props: continue
            if 'damage_per_turn' in props:
                damage = max(1, math.floor(pokemon.max_hp * props["damage_per_turn"]))
                pokemon.take_damage(damage)
                log.append(f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 因 [{effect.name}] 受到了 {damage} 点伤害！")
                if pokemon.is_fainted(): log.append(f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 倒下了！"); break 
            if 'duration' in effect.data:
                effect.data['duration'] -= 1
                if effect.data['duration'] <= 0: effects_to_remove.append((effect.id, f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 的 [{effect.name}] 效果结束了。"))
            elif 'clear_chance' in props and random.random() < props['clear_chance']:
                 effects_to_remove.append((effect.id, f"  {self._get_pokemon_log_prefix(pokemon)}{pokemon.name} 从 [{effect.name}] 中恢复了！"))
        for effect_id, msg in effects_to_remove: pokemon.remove_effect(effect_id); log.append(msg)

    def _perform_action_attack(self, attacker: Pokemon, defender: Pokemon, move: Move, log: list):
        prefix = self._get_pokemon_log_prefix(attacker)
        log.append(f"{prefix}{attacker.name} 使用了 {move.name}！")
        if self._check_hit(attacker, defender, move):
            self.execute_effect_list(move.effects, attacker, defender, move, log)
            if defender.is_fainted(): log.append(f"  {self._get_pokemon_log_prefix(defender)}{defender.name} 倒下了！")
        else:
            if defender.has_effect("evasion_shield"): log.append(f"  但 {self._get_pokemon_log_prefix(defender)}{defender.name} 的闪避架势躲开了攻击！")
            else: log.append("  但攻击落空了！")

    def _perform_action_switch(self, p_out: Pokemon, p_in: Pokemon, log: list):
        prefix = self._get_pokemon_log_prefix(p_out)
        log.append(f"{prefix}收回了 {p_out.name}！"); p_out.on_switch_out()
        self._clear_history_for(p_out) # 清空历史
        if p_out in self.player_team: self.player_active_pokemon = p_in
        else: self.npc_active_pokemon = p_in
        log.append(f"{self._get_pokemon_log_prefix(p_in)}去吧，{p_in.name}！")

    def _process_post_action_triggers(self, actor: Pokemon, opponent: Pokemon, log: list):
        if actor.is_fainted(): return
        active_sequences = actor.get_effects_by_category("sequence")
        if not active_sequences: return
        sorted_sequences = sorted(active_sequences, key=lambda eff: eff.data.get("source_slot_index", 99))
        for sequence in sorted_sequences:
            current_opponent = self.npc_active_pokemon if actor == self.player_active_pokemon else self.player_active_pokemon
            if not current_opponent or current_opponent.is_fainted(): break
            if sequence.data.get("is_activation_turn"): continue
            sequence_id = sequence.data.get("sequence_id"); charges = sequence.data.get("charges", 0)
            if not sequence_id or charges <= 0: continue
            steps = self.factory.get_follow_up_sequence(sequence_id)
            if not steps: actor.remove_effect(sequence.id); continue
            
            # 【修复】将 UnboundLocalError 的问题代码拆分为两行，确保变量在使用前被赋值
            total_charges = sequence.data.get("total_charges", len(steps))
            step_index = total_charges - charges
            
            if step_index < len(steps):
                log.append(f"  由 [{sequence.source_move or '序列'}] 追击 - 第 {step_index + 1}/{total_charges} 段：")
                self.execute_effect_list(steps[step_index], actor, current_opponent, Move("追击效果", {}, {}), log)
                if current_opponent.is_fainted():
                    log.append(f"  {self._get_pokemon_log_prefix(current_opponent)}{current_opponent.name} 倒下了！")
                    # 【核心逻辑】如果追击链条中目标被击倒，应立即中止后续的追击
                    break 
                if charges == 1:
                    actor.remove_effect(sequence.id)
                    log.append(f"  {self._get_pokemon_log_prefix(actor)}{actor.name} 的 [{sequence.source_move}] 序列结束了。")
                else: sequence.data["charges"] -= 1

    def _check_hit(self, attacker: Pokemon, defender: Pokemon, move: Move) -> bool:
        if move.guaranteed_hit: return True
        if defender.has_effect("evasion_shield"): return False
        accuracy = move.accuracy or 100
        return random.randint(1, 100) <= accuracy
    
    def _check_critical_hit(self, a: Pokemon) -> bool: 
        p, b, m = 0.0005, 0.0525, 1.5 if a.crit_rate_stage > 0 else 1.0
        return random.random() < min((a.crit_points * p + b) * m, 1.0)
    
    def calculate_damage(self, attacker: Pokemon, defender: Pokemon, move: Move) -> Dict[str, Any]:
        result = {"damage": 0, "log_msg": "", "is_crit": False}
        if move.category == MoveCategory.STATUS: return result
        power = move.display_power
        effectiveness = TypeEffectiveness.get_effectiveness(move.type, defender.types)
        if effectiveness == 0:
            result["log_msg"] = f"这对 {self._get_pokemon_log_prefix(defender)}{defender.name} 没有任何效果！"; return result
        attack_stat, defense_stat = (attacker.get_modified_stat(Stat.ATTACK), defender.get_modified_stat(Stat.DEFENSE)) if move.category == MoveCategory.PHYSICAL else (attacker.get_modified_stat(Stat.SPECIAL_ATTACK), defender.get_modified_stat(Stat.SPECIAL_DEFENSE))
        damage = (((2 * attacker.level / 5 + 2) * power * attack_stat / defense_stat) / 50) + 2
        if self._check_critical_hit(attacker):
            damage *= 2.0; result["is_crit"] = True; result["log_msg"] += "击中了要害！"
        damage *= random.uniform(0.85, 1.0)
        if move.type in attacker.types: damage *= 1.5
        damage *= effectiveness
        if effectiveness > 1: result["log_msg"] += " 效果绝佳！"
        elif effectiveness < 1: result["log_msg"] += " 效果不理想..."
        result["damage"], result["log_msg"] = math.floor(max(1, damage)), result["log_msg"].strip()
        return result
    
    def execute_effect_list(self, effect_list: List[Dict], attacker: Pokemon, defender: Pokemon, move: Move, log: list):
        if not effect_list or defender.is_fainted(): return
        for effect_data in effect_list:
            handler_class = self.effect_handler_classes.get(effect_data.get("handler"))
            if handler_class and random.randint(1, 100) <= effect_data.get("chance", 100): 
                effect_instance = handler_class(self, effect_data)
                effect_instance.execute(attacker, defender, move, log)
                if defender.is_fainted(): break