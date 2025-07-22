# service.py
import json
from pathlib import Path
from typing import Dict, Optional, Any, List, TYPE_CHECKING
from dataclasses import dataclass, field

from . import ui
from .battle_logic.factory import GameDataFactory
from .battle_logic.battle import Battle
from .battle_logic.pokemon import Pokemon
from .battle_logic.constants import BattleState
from astrbot.api import logger

if TYPE_CHECKING:
    from .battle_logic.battle import Battle

@dataclass
class ServiceResult:
    success: bool; message: str; log_level: Optional[str] = None

@dataclass
class GameSession:
    state: BattleState = BattleState.SELECTING
    team_config: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    battle: Optional[Battle] = None
    
    def is_selecting(self) -> bool: return self.state == BattleState.SELECTING
    def is_fighting(self) -> bool: return self.state == BattleState.FIGHTING
    def is_awaiting_switch(self) -> bool: return self.state == BattleState.AWAITING_SWITCH

class GameService:
    def __init__(self, factory: GameDataFactory, npc_team_config: List[Dict]):
        self.factory = factory
        self.npc_team_config = npc_team_config
        self.sessions: Dict[str, GameSession] = {}

    def get_session_and_battle(self, session_id: str) -> tuple[Optional[GameSession], Optional[Battle]]:
        session = self.sessions.get(session_id)
        if not session: return None, None
        return session, session.battle

    def _find_target_pokemon(self, battle: Battle, target_str: str) -> Optional[Pokemon]:
        try:
            target_num = int(target_str)
            if 1 <= target_num <= len(battle.player_team):
                pokemon = battle.player_team[target_num - 1]
                if not pokemon.is_fainted(): return pokemon
        except (ValueError, IndexError): pass
        return next((p for p in battle.get_player_survivors() if p.name == target_str), None)

    def _handle_turn_result(self, session_id: str, session: GameSession, battle: Battle, result: Dict) -> ServiceResult:
        turn_log = result.get('log', '')
        session.state = result["state"]
        if result.get("is_over"):
            winner_name = "玩家" if result.get('winner') == 'Player' else 'NPC'
            winner_msg = f"🏆 **{winner_name} 获得了胜利！** 🏆"
            final_log = f"{turn_log}\n\n{winner_msg}"
            if session_id in self.sessions: del self.sessions[session_id]
            return ServiceResult(success=True, message=final_log)
        if battle.npc_active_pokemon and battle.npc_active_pokemon.is_fainted():
            next_npc = battle.get_next_npc_pokemon()
            if next_npc:
                battle.npc_active_pokemon = next_npc
                turn_log += f"\n\n(NPC) 派出了新的宝可梦：{next_npc.name}！"
        ui_body = ui.generate_regular_ui_body(session)
        final_message = ui.generate_final_message(ui_body, session, turn_log=turn_log)
        return ServiceResult(success=True, message=final_message)

    def start_new_selection(self, session_id: str) -> ServiceResult:
        if session_id in self.sessions: return ServiceResult(False, "你已经在一个会话中了！使用 /battle flee 放弃当前对战。")
        self.sessions[session_id] = GameSession()
        header = "⚔️ **队伍选择开始！** ⚔️"
        instructions = ["1. 使用 `/battle add [宝可梦名]` 将宝可梦加入队伍 (最多6只)。", "2. (可选) 使用 `/battle setmove <精灵名> <旧技能> <新技能>` 更换技能。", "3. 准备好后，使用 `/battle ready [首发宝可梦名]` 开始战斗！"]
        pokemon_list_msg = ui.generate_pokemon_list_msg(self.factory.get_all_pokemon_names())
        full_message = "\n\n".join([header, "\n".join(instructions), pokemon_list_msg])
        return ServiceResult(True, full_message)

    def add_pokemon_to_team(self, session_id: str, names_to_add: List[str]) -> ServiceResult:
        session = self.sessions.get(session_id)
        if not session or not session.is_selecting(): return ServiceResult(False, "请先使用 `/battle start` 开始选择队伍。")
        team = session.team_config; added_log, error_log = [], []
        for name in names_to_add:
            if len(team) >= 6: error_log.append("队伍已满（最多6只）！"); break
            pokemon_data_model = self.factory.get_pokemon_data(name)
            if not pokemon_data_model: error_log.append(f"未找到宝可梦 '{name}'"); continue
            if name in team: error_log.append(f"'{name}' 已在你的队伍中"); continue
            session.team_config[name] = { "current": pokemon_data_model.default_moves[:4], "extra": pokemon_data_model.extra_moves }; added_log.append(f"`{name}`")
        response_parts = []
        if added_log: response_parts.append(f"✅ 成功添加: {', '.join(added_log)}")
        if error_log: response_parts.append(f"❌ 出现问题: {', '.join(error_log)}")
        response_parts.append("\n" + ui.generate_team_moves_details_msg(session.team_config)); response_parts.append("\n(可选) 使用 `/battle setmove <精灵名> <旧技能> <新技能>` 更换技能。")
        response_parts.append("队伍组建完成后，使用 `/battle ready [首发宝可梦名]` 开始战斗！")
        return ServiceResult(True, "\n".join(response_parts))

    def set_pokemon_move(self, session_id: str, pokemon_name: str, forget_move: str, learn_move: str) -> ServiceResult:
        session = self.sessions.get(session_id)
        if not session or not session.is_selecting(): return ServiceResult(False, "只能在队伍选择阶段更换技能。")
        team = session.team_config
        if pokemon_name not in team: return ServiceResult(False, f"你的队伍中没有 `{pokemon_name}`。")
        pmoves = team[pokemon_name]; current, extra = pmoves.get("current", []), pmoves.get("extra", [])
        if forget_move not in current: return ServiceResult(False, f"`{pokemon_name}` 当前不会技能 `{forget_move}`。")
        if learn_move not in extra: return ServiceResult(False, f"`{pokemon_name}` 无法学会技能 `{learn_move}`。")
        current[current.index(forget_move)], extra[extra.index(learn_move)] = learn_move, forget_move
        details_msg = ui.generate_team_moves_details_msg(session.team_config)
        full_message = f"✅ 技能更换成功！\n\n你的 `{pokemon_name}` 忘记了 `{forget_move}`，学会了 `{learn_move}`！\n\n{details_msg}\n\n队伍组建完成后，使用 `/battle ready [首发宝可梦名]` 开始战斗！"
        return ServiceResult(True, full_message)

    def ready_and_start_battle(self, session_id: str, starter_name: str) -> ServiceResult:
        session = self.sessions.get(session_id)
        if not session or not session.is_selecting(): return ServiceResult(False, "请先使用 `/battle start`。")
        team_config = session.team_config
        if not (1 <= len(team_config) <= 6): return ServiceResult(False, "队伍数量需为1-6只！")
        if starter_name not in team_config: return ServiceResult(False, f"首发宝可梦 '{starter_name}' 必须在你的队伍中！")
        player_team = [self.factory.create_pokemon(name, 100, data['current']) for name, data in team_config.items()]; player_team.sort(key=lambda p: p.name != starter_name)
        npc_team: List[Pokemon] = []
        for npc_config in self.npc_team_config:
            npc_pokemon = self.factory.create_pokemon(npc_config["name"], 100, npc_config.get("moves") or None)
            if npc_pokemon: npc_team.append(npc_pokemon)
            else: logger.warning(f"无法为 NPC 创建宝可梦 '{npc_config['name']}'。")
        if not npc_team: return ServiceResult(False, "❌ 错误：无法创建任何NPC宝可梦。\n请在插件后台配置中至少填写一名有效（有名称）的NPC宝可梦，并确保已点击保存。", log_level="error")
        battle = Battle(player_team, npc_team, self.factory)
        session.battle = battle; session.state = BattleState.FIGHTING
        team_numbered = "\n".join([f"  {i+1}. `{p.name}`" for i, p in enumerate(player_team)])
        log = f"⚔️ 战斗开始！ ⚔️\n\n你的队伍编号：\n{team_numbered}"; ui_body = ui.generate_regular_ui_body(session)
        full_message = ui.generate_final_message(ui_body, session, turn_log=log)
        return ServiceResult(True, full_message)

    def flee_battle(self, session_id: str) -> ServiceResult:
        if session_id in self.sessions: del self.sessions[session_id]; return ServiceResult(True, "你从战斗中逃跑了，对战结束！")
        return ServiceResult(False, "你当前不在任何对战中。")

    def execute_attack(self, session_id: str, move_name: str) -> ServiceResult:
        session, battle = self.get_session_and_battle(session_id)
        if not session or not battle or not session.is_fighting(): return ServiceResult(False, "现在不是行动的时候。")
        player = battle.player_active_pokemon
        
        if not player.has_usable_moves():
            player_action_intent = {"type": "struggle"}
        else:
            move = player.get_move_by_name(move_name)
            if not move:
                return ServiceResult(False, f"你的 {player.name} 不会技能 '{move_name}'！")
            if move.current_pp <= 0:
                return ServiceResult(False, f"技能 `{move_name}` 的PP已经用完了！")
            player_action_intent = {"type": "attack", "data": move}

        # 【核心修复】调用 battle.py 中新的、统一的回合处理方法
        result = battle.process_turn(player_action_intent)
        return self._handle_turn_result(session_id, session, battle, result)

    def execute_switch(self, session_id: str, target_str: Optional[str]) -> ServiceResult:
        session, battle = self.get_session_and_battle(session_id)
        if not session or not battle: return ServiceResult(False, "你不在任何对战中。")
        if not session.is_fighting() and not session.is_awaiting_switch(): return ServiceResult(False, "现在不是切换宝可梦的时候！")
        if not target_str: return ServiceResult(True, ui.display_full_team_status(battle))
            
        target = self._find_target_pokemon(battle, target_str)
        if not target: return ServiceResult(False, f"无法切换: '{target_str}' 不是一个有效的、存活的宝可梦名称或队伍编号。")
        if target == battle.player_active_pokemon: return ServiceResult(False, "不能切换到已经在场上的宝可梦！")
            
        if session.is_fighting():
            # 【核心修复】将换人也视为一种“行动意图”
            player_action_intent = {"type": "switch", "data": target}
            result = battle.process_turn(player_action_intent)
            return self._handle_turn_result(session_id, session, battle, result)
        elif session.is_awaiting_switch():
            battle.player_active_pokemon = target; session.state = BattleState.FIGHTING
            log = f"你派出了 {target.name}！"
            ui_body = ui.generate_regular_ui_body(session)
            full_message = ui.generate_final_message(ui_body, session, turn_log=log)
            return ServiceResult(True, full_message)
        else:
            return ServiceResult(False, "现在不是切换宝可梦的时候！")