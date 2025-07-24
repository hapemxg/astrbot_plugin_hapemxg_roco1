# tests/test_scenario_11_hit_evasion_priority.py (已修复测试隔离问题)
import pytest
from pathlib import Path
from copy import deepcopy

from astrbot_plugin_hapemxg_roco1.battle_logic.battle import Battle
from astrbot_plugin_hapemxg_roco1.battle_logic.pokemon import Pokemon
from astrbot_plugin_hapemxg_roco1.battle_logic.factory import GameDataFactory
from astrbot_plugin_hapemxg_roco1.battle_logic.move import Move
from astrbot_plugin_hapemxg_roco1.battle_logic.data_models import MoveDataModel

# --- Fixture 和辅助函数 (保持不变) ---
@pytest.fixture(scope="function")
def game_factory() -> GameDataFactory:
    plugin_root = Path(__file__).parent.parent
    test_data_path = plugin_root / "tests" / "test_data"
    if not test_data_path.exists():
        test_data_path = plugin_root / "data"
        if not test_data_path.exists():
             pytest.fail(f"测试数据目录 'tests/test_data' 或 'data' 未找到")
    return deepcopy(GameDataFactory(test_data_path))

def assert_log_contains(log: str, expected: str):
    assert expected in log, f"日志未找到期望内容: '{expected}'\n完整日志:\n---\n{log}\n---"

def assert_log_not_contains(log: str, unexpected: str):
    assert unexpected not in log, f"日志中出现了不应有的内容: '{unexpected}'\n完整日志:\n---\n{log}\n---"


@pytest.mark.asyncio
async def test_hit_evasion_priority_logic(game_factory: GameDataFactory):
    """
    【核心测试剧本】验证命中与闪避的精确优先级规则。
    - 场景A: 必中技能 (guaranteed_hit: true) vs 闪避状态 -> 结果：必定命中
    - 场景B: 100%命中率技能 (accuracy: 100) vs 闪避状态 -> 结果：必定闪避
    """
    # --- Arrange: 准备测试环境 ---

    game_factory._effects_db["evasion_shield"] = {
        "name": "闪避架势", "category": "marker", "is_temporary": True,
        "guaranteed_evasion": True, "apply_log": "摆出了闪避的架势！"
    }

    attacker = game_factory.create_pokemon("测试精灵", 100)
    defender = game_factory.create_pokemon("测试精灵2", 100)
    
    # 【关键修复】让 NPC "失忆"，使其在本回合无法行动，防止日志污染
    defender.skill_slots = []

    guaranteed_hit_move = Move(
        name="锁定打击",
        display={"power": 60, "pp": 20, "type": "钢", "category": "special"},
        on_use={"accuracy": None, "guaranteed_hit": True, "effects": [{"handler": "deal_damage", "options": {"power": 60}}]}
    )
    normal_hit_move = Move(
        name="精准光束",
        display={"power": 60, "pp": 20, "type": "一般", "category": "special"},
        on_use={"accuracy": 100, "guaranteed_hit": False, "effects": [{"handler": "deal_damage", "options": {"power": 60}}]}
    )
    # 【修复】为动态创建的技能添加伤害效果，否则 "造成了" 永远不会出现
    guaranteed_hit_move.effects = [{"handler": "deal_damage", "options": {"power": 60}}]
    normal_hit_move.effects = [{"handler": "deal_damage", "options": {"power": 60}}]


    # --- 场景 A: 必中技能 vs 闪避状态 ---
    print("\n--- 开始场景 A: 必中技能 vs 闪避状态 ---")
    
    battle_a = Battle([deepcopy(attacker)], [deepcopy(defender)], game_factory)
    defender_a = battle_a.npc_active_pokemon
    defender_a.apply_effect("evasion_shield")
    assert defender_a.get_effect("evasion_shield") is not None, "场景A准备失败: 未能施加闪避状态"

    log_a = battle_a.process_turn({"type": "attack", "data": guaranteed_hit_move})["log"]
    
    assert_log_contains(log_a, "使用了 锁定打击！")
    assert_log_contains(log_a, "造成了")
    assert_log_not_contains(log_a, "但攻击落空了！")
    print("--- 场景 A 测试通过 ---")

    # --- 场景 B: 100%命中率技能 vs 闪避状态 ---
    print("\n--- 开始场景 B: 100%命中率技能 vs 闪避状态 ---")
    
    battle_b = Battle([deepcopy(attacker)], [deepcopy(defender)], game_factory)
    defender_b = battle_b.npc_active_pokemon
    defender_b.apply_effect("evasion_shield")
    assert defender_b.get_effect("evasion_shield") is not None, "场景B准备失败: 未能施加闪避状态"
    
    log_b = battle_b.process_turn({"type": "attack", "data": normal_hit_move})["log"]
    
    assert_log_contains(log_b, "使用了 精准光束！")
    assert_log_contains(log_b, "但攻击落空了！")
    assert_log_not_contains(log_b, "造成了")
    print("--- 场景 B 测试通过 ---")