# ui.py (已重构以完全兼容Aura/Component架构)

from typing import Dict, Optional, List, Any, TYPE_CHECKING

# 避免循环导入，仅在类型检查时导入GameSession
if TYPE_CHECKING:
    from .service import GameSession
    from .battle_logic.battle import Battle
    from .battle_logic.pokemon import Pokemon

# 从正确的模块导入常量和组件
from .battle_logic.constants import Stat, MoveCategory, STAT_NAME_MAP
from .battle_logic.components import StatusEffectComponent, StatStageComponent

# --- UI 格式化辅助函数 ---

def format_statuses(p: 'Pokemon') -> str:
    """
    格式化宝可梦的所有效果显示。
    现在从宝可梦的Aura中读取StatusEffectComponent。
    """
    status_components = p.aura.get_components(StatusEffectComponent)
    if not status_components:
        return ""
    
    # 通过宝可梦实例注入的 factory 访问效果属性
    effect_properties = p.factory.get_effect_properties()
    
    # 只显示那些被定义为“异常状态”的效果
    status_names = [
        comp.name for comp in status_components 
        if effect_properties.get(comp.effect_id, {}).get('category') == 'status'
    ]
    return "".join([f"[{name}]" for name in status_names])

def format_stages(p: 'Pokemon') -> str:
    """
    格式化宝可梦的能力等级变化。
    现在从宝可梦的Aura中读取StatStageComponent。
    """
    parts = []
    
    # 从Aura中获取所有的能力等级变化组件
    stage_components = p.aura.get_components(StatStageComponent)
    
    # 汇总每个能力的总变化量
    total_stages: Dict[Stat, int] = {}
    for comp in stage_components:
        total_stages[comp.stat] = total_stages.get(comp.stat, 0) + comp.change

    for stat, value in total_stages.items():
        if value != 0 and stat in STAT_NAME_MAP:
            # 排除暴击率，它将单独处理
            if stat == Stat.CRIT_RATE: continue
            parts.append(f"{STAT_NAME_MAP[stat]} {'+' if value > 0 else ''}{value}")
    
    crit_stage_total = total_stages.get(Stat.CRIT_RATE, 0)
    if crit_stage_total > 0:
        parts.append(f"暴击率 +{crit_stage_total}")

    if parts:
        return f"  强化: [ {', '.join(parts)} ]"
    return ""

def format_pokemon_details(p: Optional['Pokemon']) -> str:
    """
    格式化单个宝可梦的核心信息（不含技能）。
    此函数现在依赖于已修复的下层函数。
    """
    if not p:
        return "  (无)"
    
    types_str = "/".join(p.types)
    status_str = format_statuses(p)
    
    title_line = f"`{p.name}` ({types_str}) (Lv.{p.level}) {status_str}".strip()
    
    stats_str = (f"  攻击: {p.get_modified_stat(Stat.ATTACK)} | 防御: {p.get_modified_stat(Stat.DEFENSE)}\n"
                 f"  特攻: {p.get_modified_stat(Stat.SPECIAL_ATTACK)} | 特防: {p.get_modified_stat(Stat.SPECIAL_DEFENSE)}\n"
                 f"  速度: {p.get_modified_stat(Stat.SPEED)}")
    
    stages_str = format_stages(p)
    
    # HP现在通过属性直接访问，它会在内部通过Aura计算
    final_parts = [title_line, f"HP: {p.current_hp}/{p.max_hp}", stats_str]
    if stages_str:
        final_parts.append(stages_str)
        
    return "\n".join([f"  {line}" for line in "\n".join(final_parts).split('\n')])

def format_full_pokemon_status(p: Optional['Pokemon']) -> str:
    """
    格式化单个宝可梦的完整信息（包含技能）。
    """
    if not p:
        return ""
        
    details_str = format_pokemon_details(p)
    
    moves_info = ["\n  **技能:**"]
    # 技能现在存储在 skill_slots 中
    if p.skill_slots:
        for slot in p.skill_slots:
            move = slot.move
            category_text = {"physical": "物理", "special": "特殊", "status": "变化"}.get(move.category, "未知")
            details = f"{move.type}/{category_text}"
            
            if move.category != MoveCategory.STATUS and move.display_power > 0:
                details += f"/{move.display_power}威力"
            
            details += f"/{move.accuracy}命中" if move.accuracy is not None else "/--命中"
            
            # PP现在通过 get_current_pp 方法访问
            pp_val = p.get_current_pp(move.name)
            pp_str = f"(PP: {pp_val}/{move.max_pp})" if move.max_pp is not None else "(PP: --/--)"
            
            moves_info.append(f"    - {move.name} ({details}) {pp_str}")
    else:
        moves_info.append("    (无)")
        
    return details_str + "\n" + "\n".join(moves_info)

def generate_regular_ui_body(session: 'GameSession') -> str:
    """
    生成常规战斗界面的核心部分。
    """
    battle: 'Battle' = session.battle
    if not battle: return "错误：战斗实例未找到。"

    def _format_team_overview(team: List['Pokemon']) -> str:
        return ", ".join([f"{'☠️' if p.is_fainted() else '🟢'} `{p.name}`" for p in team])

    player, npc = battle.player_active_pokemon, battle.npc_active_pokemon
    
    player_full_status = format_full_pokemon_status(player)
    
    status_parts = [
        "**👤 你的状态**", 
        player_full_status, 
        f"**队伍概览:** {_format_team_overview(battle.player_team)}",
        "\n" + ("-"*20) + "\n", 
        "**🤖 NPC状态**", 
        format_pokemon_details(npc), 
        f"**队伍概览:** {_format_team_overview(battle.npc_team)}"
    ]
    return "\n".join(status_parts)

def generate_final_message(ui_body: str, session: 'GameSession', turn_log: str = "") -> str:
    """将UI核心和行动提示组合成最终消息。"""
    final_message = (f"```\n{turn_log}\n```\n" if turn_log else "") + ui_body
    battle: 'Battle' = session.battle
    if not battle: return final_message # 安全返回
    
    player = battle.player_active_pokemon
    action_prompts = []

    if session.is_fighting() and player and not player.is_fainted():
        # 【核心修改】当所有技能PP耗尽时，提供特殊选项
        if not player.has_usable_moves():
            action_prompts = [
                "你的宝可梦所有技能PP都用完了！",
                "你可以选择:",
                "/attack 无法行动 (本回合不行动，但可触发被动效果)",
                "/battle switch [名字/编号] (切换宝可梦)",
                "/battle flee (逃跑)"
            ]
        elif not battle.is_over(): # 确保战斗未结束才显示常规指令
            action_prompts = ["使用以下指令行动:", "/attack [技能名]", "/battle switch [名字/编号]", "/battle flee"]
    elif session.is_awaiting_switch():
        survivors = battle.get_player_survivors()
        survivor_info = ", ".join([f"{i+1}.`{p.name}`" for i, p in enumerate(battle.player_team) if p in survivors])
        action_prompts = [f"你的宝可梦倒下了！请选择下一只：{survivor_info}", "使用 `/battle switch [名字/编号]` 来继续。"]
    
    if action_prompts: 
        final_message += "\n\n" + "\n".join(action_prompts)
    return final_message

def display_full_team_status(battle: 'Battle') -> str:
    """显示玩家完整队伍的状态。"""
    response_parts = ["**-- 队伍状态概览 --**"]
    for i, p in enumerate(battle.player_team):
        status_hint = " (已倒下)" if p.is_fainted() else " (场上)" if p == battle.player_active_pokemon else ""
        response_parts.append(f"\n**{i+1}. `{p.name}`**{status_hint}")
        response_parts.append(format_full_pokemon_status(p))
    
    # 【修改】当所有PP耗尽时，也显示正确的指令提示
    if battle.player_active_pokemon and not battle.player_active_pokemon.has_usable_moves():
        response_parts.append("\n所有技能PP已用完！\n/attack 无法行动 (不行动)\n/battle switch [名字/编号] (切换宝可梦)\n/battle flee (逃跑)")
    else:
        response_parts.append("\n使用以下指令行动:\n/attack [技能名]\n/battle switch [名字/编号]\n/battle flee")
    return "\n".join(response_parts)

def generate_pokemon_list_msg(pokemon_names: List[str]) -> str:
    """生成可选择的宝可梦列表消息。"""
    return "可选择的宝可梦有：\n" + "\n".join([f"  - `{name}`" for name in pokemon_names])

def generate_team_moves_details_msg(team_config: Dict[str, Dict[str, List[str]]]) -> str:
    """生成队伍选择阶段的队伍和技能详情消息。"""
    if not team_config: 
        return "你当前的队伍是空的。"
    
    response_parts = [f"你当前的队伍 ({len(team_config)}/6):"]
    for name, move_data in team_config.items():
        response_parts.append(f"\n- **`{name}`**")
        response_parts.append("  当前技能: " + ", ".join([f"`{m}`" for m in move_data['current']]))
        extra_moves = move_data.get("extra", [])
        if extra_moves:
            response_parts.append("  可学技能: " + ", ".join([f"`{em}`" for em in extra_moves]))
    
    return "\n".join(response_parts)