# astrphot_plugin_hapemxg_roco1/ui.py

from typing import Dict, Optional, List, Any, TYPE_CHECKING
from .battle_logic.battle import Battle
from .battle_logic.pokemon import Pokemon
# 【核心修复】将导入 STATUS_PROPERTIES 替换为 EFFECT_PROPERTIES
from .battle_logic.constants import BattleState, Stat, EFFECT_PROPERTIES, MoveCategory, STAT_NAME_MAP

if TYPE_CHECKING:
    from .service import GameSession

# --- UI 格式化辅助函数 (此部分需修改) ---

def format_statuses(p: Pokemon) -> str:
    """【重构】格式化宝可梦的所有效果显示。"""
    if not p.effects:
        return ""
    # 只显示那些被定义为“异常状态”的效果
    status_names = [eff.name for eff in p.effects if EFFECT_PROPERTIES.get(eff.id, {}).get('category') == 'status']
    return "".join([f"[{name}]" for name in status_names])

# ... (其他 UI 函数 format_stages, format_pokemon_details 等保持不变) ...
def format_stages(p: Pokemon) -> str:
    """格式化宝可梦的能力等级和暴击等级变化。"""
    parts = []
    
    for stat, value in p.stat_stages.items():
        if value != 0 and stat in STAT_NAME_MAP:
            parts.append(f"{STAT_NAME_MAP[stat]} {'+' if value > 0 else ''}{value}")
    
    if p.crit_rate_stage > 0:
        parts.append(f"暴击率 +{p.crit_rate_stage}")

    if parts:
        return f"  强化: [ {', '.join(parts)} ]"
    return ""

def format_pokemon_details(p: Optional[Pokemon]) -> str:
    """格式化单个宝可梦的核心信息（不含技能）。"""
    if not p:
        return "  (无)"
    
    types_str = "/".join(p.types)
    status_str = format_statuses(p)
    
    title_line = f"`{p.name}` ({types_str}) (Lv.{p.level}) {status_str}".strip()
    
    stats_str = (f"  攻击: {p.get_modified_stat(Stat.ATTACK)} | 防御: {p.get_modified_stat(Stat.DEFENSE)}\n"
                 f"  特攻: {p.get_modified_stat(Stat.SPECIAL_ATTACK)} | 特防: {p.get_modified_stat(Stat.SPECIAL_DEFENSE)}\n"
                 f"  速度: {p.get_modified_stat(Stat.SPEED)}")
    
    stages_str = format_stages(p)
    
    final_parts = [title_line, f"HP: {p.current_hp}/{p.max_hp}", stats_str]
    if stages_str:
        final_parts.append(stages_str)
        
    return "\n".join([f"  {part}" if isinstance(part, str) else "\n".join(f"  {line}" for line in part.split('\n')) for part in final_parts])

# ... (后续所有UI函数 generate_regular_ui_body, generate_final_message 等都不再需要修改) ...
# (此处省略未修改的UI函数)
def format_full_pokemon_status(p: Optional[Pokemon]) -> str:
    """格式化单个宝可梦的完整信息（包含技能）。"""
    if not p:
        return ""
        
    details_str = format_pokemon_details(p)
    
    moves_info = ["\n  **技能:**"]
    if p.moves:
        for name, move in p.moves.items():
            category_text = {"physical": "物理", "special": "特殊", "status": "变化"}.get(move.category, "未知")
            details = f"{move.type}/{category_text}"
            
            if move.category != MoveCategory.STATUS and move.display_power > 0:
                details += f"/{move.display_power}威力"
            
            details += f"/{move.accuracy}命中" if move.accuracy is not None else "/--命中"
            
            moves_info.append(f"    - {name} ({details}) (PP: {move.current_pp}/{move.max_pp})")
    else:
        moves_info.append("    (无)")
        
    return details_str + "\n" + "\n".join(moves_info)

def generate_regular_ui_body(session: 'GameSession') -> str:
    battle: Battle = session.battle
    if not battle: return "错误：战斗实例未找到。"
    def _format_team_overview(team: List[Pokemon]) -> str:
        return ", ".join([f"{'☠️' if p.is_fainted() else '🟢'} `{p.name}`" for p in team])
    player, npc = battle.player_active_pokemon, battle.npc_active_pokemon
    player_full_status = format_full_pokemon_status(player) if player and not player.is_fainted() else format_pokemon_details(player)
    status_parts = [
        "**👤 你的状态**", player_full_status, f"**队伍概览:** {_format_team_overview(battle.player_team)}",
        "\n" + ("-"*20) + "\n", "**🤖 NPC状态**", format_pokemon_details(npc), f"**队伍概览:** {_format_team_overview(battle.npc_team)}"
    ]
    return "\n".join(status_parts)

def generate_final_message(ui_body: str, session: 'GameSession', turn_log: str = "") -> str:
    final_message = (f"```\n{turn_log}\n```\n" if turn_log else "") + ui_body
    battle: Battle = session.battle; player = battle.player_active_pokemon
    action_prompts = []
    if session.is_fighting() and player and not player.is_fainted() and not battle.is_over():
        action_prompts = ["使用以下指令行动:", "/attack [技能名]", "/battle switch [名字/编号]", "/battle flee"]
    elif session.is_awaiting_switch():
        survivors = [p for p in battle.player_team if not p.is_fainted()]
        survivor_info = ", ".join([f"{i+1}.`{p.name}`" for i, p in enumerate(battle.player_team) if p in survivors])
        action_prompts = [f"你的宝可梦倒下了！请选择下一只：{survivor_info}", "使用 `/battle switch [名字/编号]` 来继续。"]
    if action_prompts: final_message += "\n\n" + "\n".join(action_prompts)
    return final_message

def display_full_team_status(battle: Battle) -> str:
    response_parts = ["**-- 队伍状态概览 --**"]
    for i, p in enumerate(battle.player_team):
        status_hint = " (已倒下)" if p.is_fainted() else " (场上)" if p == battle.player_active_pokemon else ""
        response_parts.append(f"\n**{i+1}. `{p.name}`**{status_hint}")
        response_parts.append(format_full_pokemon_status(p))
    response_parts.append("\n使用以下指令行动:\n/attack [技能名]\n/battle switch [名字/编号]\n/battle flee")
    return "\n".join(response_parts)

def generate_pokemon_list_msg(pokemon_names: List[str]) -> str:
    return "可选择的宝可梦有：\n" + "\n".join([f"  - `{name}`" for name in pokemon_names])

def generate_team_moves_details_msg(team_config: Dict[str, Dict[str, List[str]]]) -> str:
    if not team_config: return "你当前的队伍是空的。"
    response_parts = [f"你当前的队伍 ({len(team_config)}/6):"]
    for name, move_data in team_config.items():
        response_parts.append(f"\n- **`{name}`**")
        response_parts.append("  当前技能: " + ", ".join([f"`{m}`" for m in move_data['current']]))
        extra_moves = move_data.get("extra", [])
        if extra_moves:
            response_parts.append("  可学技能: " + ", ".join([f"`{em}`" for em in extra_moves]))
    return "\n".join(response_parts)