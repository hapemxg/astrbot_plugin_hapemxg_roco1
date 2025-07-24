# tests/test_battle.py (已根据业务规则和测试最佳实践修正)
import pytest
import random
from pathlib import Path
from copy import deepcopy

from astrbot_plugin_hapemxg_roco1.battle_logic.battle import Battle
from astrbot_plugin_hapemxg_roco1.battle_logic.pokemon import Pokemon, SkillSlot
from astrbot_plugin_hapemxg_roco1.battle_logic.factory import GameDataFactory
from astrbot_plugin_hapemxg_roco1.battle_logic.constants import Stat
from astrbot_plugin_hapemxg_roco1.battle_logic.data_models import MoveDataModel, EffectModel
from astrbot_plugin_hapemxg_roco1.battle_logic.components import StatusEffectComponent, VolatileFlagComponent, HealComponent, DamageComponent

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

def assert_log_contains(log: str, expected: list[str]):
    last_index = -1
    for sub in expected:
        current_index = log.find(sub, last_index + 1)
        assert current_index != -1, f"日志未找到期望内容: '{sub}'\n完整日志:\n---\n{log}\n---"
        assert current_index > last_index, f"日志内容顺序错误: '{sub}' 未按预期顺序出现\n完整日志:\n---\n{log}\n---"
        last_index = current_index

def assert_log_not_contains(log: str, unexpected: list[str]):
    for sub in unexpected:
        assert sub not in log, f"日志中出现了不应有的内容: '{sub}'"

# --- 测试剧本 (已全面修正以匹配最终规则) ---

@pytest.mark.asyncio
async def test_scenario_1_volatile_effects_cleared_on_switch(game_factory: GameDataFactory):
    player_team = [
        game_factory.create_pokemon("初始精灵-test", 100),
        game_factory.create_pokemon("替换精灵-test", 100)
    ]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["冥暗诅咒"])]
    player_team[0].stats[Stat.SPEED] = 50
    npc_team[0].stats[Stat.SPEED] = 100
    battle = Battle(player_team, npc_team, game_factory)
    
    battle.process_turn({"type": "attack", "data": player_team[0].get_move_by_name("速度打击")})
    assert player_team[0].has_effect("curse")

    battle.process_turn({"type": "switch", "data": player_team[1]})
    assert battle.player_active_pokemon is player_team[1]
    assert not player_team[0].has_effect("curse")

@pytest.mark.asyncio
async def test_scenario_2_poison_damage_at_end_of_mini_turn(game_factory: GameDataFactory):
    """【已修正】断言顺序已根据“先结算异常，后行动”的规则进行调整。"""
    player_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["臭鸡蛋"])]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])]
    player_team[0].stats[Stat.SPEED] = 100
    npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)

    log1 = battle.process_turn({"type": "attack", "data": battle.player_active_pokemon.get_move_by_name("臭鸡蛋")})["log"]
    
    assert battle.npc_active_pokemon.has_effect("poison")
    assert_log_contains(log1, [
        "使用了 臭鸡蛋！",
        "陷入了 [中毒] 状态！",
        "因 [中毒] 受到了",      # 修正点：异常伤害结算在前
        "使用了 巨焰吞噬！",    # 修正点：后手方行动在后
    ])

@pytest.mark.asyncio
async def test_scenario_3_status_replacement_and_derivative_effect(game_factory: GameDataFactory):
    player_team = [game_factory.create_pokemon("测试精灵4", 100, move_names=["龙威"])]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])]
    player_team[0].stats[Stat.SPEED] = 100
    npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    npc = battle.npc_active_pokemon
    
    npc.apply_effect("paralysis")
    assert npc.has_effect("paralysis")

    log1 = battle.process_turn({"type": "attack", "data": battle.player_active_pokemon.get_move_by_name("龙威")})["log"]
    
    assert npc.has_effect("fear")
    assert not npc.has_effect("paralysis")
    assert_log_contains(log1, [
        "的 [麻痹] 状态解除了。",
        "陷入了 [恐惧]！",
        "畏缩了！",
        "畏缩了，无法行动！"
    ])

@pytest.mark.asyncio
async def test_scenario_4_sequence_refresh_is_precise(game_factory: GameDataFactory):
    player_team = [game_factory.create_pokemon("测试精灵3", 100, move_names=["测试连击1", "猛烈撞击", "龙之连舞", "破土之力"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100)]
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon

    battle.process_turn({"type": "attack", "data": player.get_move_by_name("测试连击1")})
    assert player.get_effect("sequence_slot_0").data["charges"] == 2

    battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})
    assert player.get_effect("sequence_slot_0").data["charges"] == 1
    assert player.get_effect("sequence_slot_2").data["charges"] == 2

    log = battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})["log"]

    assert_log_contains(log, ["由 [测试连击1] 追击", "的 [测试连击1] 序列结束了"])
    assert not player.has_effect("sequence_slot_0")
    assert player.get_effect("sequence_slot_2").data["charges"] == 2

@pytest.mark.asyncio
async def test_scenario_5_sequence_execution_order_and_initial_hit(game_factory: GameDataFactory):
    player_team = [game_factory.create_pokemon("测试精灵3", 100, move_names=["测试连击1", "猛烈撞击", "龙之连舞", "破土之力"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])]
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon

    log1 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})["log"]
    assert_log_not_contains(log1, ["由 [龙之连舞] 追击"])
    assert player.get_effect("sequence_slot_2") is not None

    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("测试连击1")})["log"]
    assert_log_contains(log2, ["由 [龙之连舞] 追击"])
    assert_log_not_contains(log2, ["由 [测试连击1] 追击"])
    assert player.get_effect("sequence_slot_0") is not None
    assert player.get_effect("sequence_slot_2").data["charges"] == 1

    log3 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("猛烈撞击")})["log"]
    assert_log_contains(log3, ["由 [测试连击1] 追击", "由 [龙之连舞] 追击"])

@pytest.mark.asyncio
async def test_scenario_6_pp_consumption_logic(game_factory: GameDataFactory, monkeypatch):
    player_A = game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])
    npc_A = game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])
    battle_A = Battle([player_A], [npc_A], game_factory)
    initial_pp_A = npc_A.get_current_pp("巨焰吞噬")
    battle_A.process_turn({"type": "attack", "data": player_A.get_move_by_name("猛烈撞击")})
    assert npc_A.get_current_pp("巨焰吞噬") == initial_pp_A - 1

    player_B = game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])
    npc_B = game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])
    battle_B = Battle([player_B], [npc_B], game_factory)
    npc_B.apply_effect("paralysis")
    initial_pp_B = npc_B.get_current_pp("巨焰吞噬")
    
    monkeypatch.setattr(random, "random", lambda: 0.01)
    
    log = battle_B.process_turn({"type": "attack", "data": player_B.get_move_by_name("猛烈撞击")})["log"]
    
    assert_log_contains(log, ["全身麻痹，无法行动！"])
    assert npc_B.get_current_pp("巨焰吞噬") == initial_pp_B

@pytest.mark.asyncio
async def test_scenario_7_active_move_kill_prevents_follow_up(game_factory: GameDataFactory):
    """【已通过】此测试用例现在可以正确验证：主动行动击倒对手会立即终止回合。"""
    player_team = [game_factory.create_pokemon("测试精灵4", 100, move_names=["龙之连舞", "速度打击"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100)]
    
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon
    
    battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})
    assert player.has_effect("sequence_slot_0")

    npc_team[0].aura._components = [c for c in npc_team[0].aura._components if not isinstance(c, HealComponent)]
    npc_team[0].aura.add_component(DamageComponent(npc_team[0].max_hp - 1))

    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("速度打击")})["log"]
    
    assert_log_contains(log2, ["使用了 速度打击！", "测试精灵 倒下了！"])
    assert_log_not_contains(log2, ["由 [龙之连舞] 追击"])

@pytest.mark.asyncio
async def test_scenario_8_sequence_chain_is_interrupted_on_kill(game_factory: GameDataFactory):
    """【已修正】使用直接施加效果的方式准备测试环境，避免副作用。"""
    # --- Arrange: 准备测试数据和环境 ---
    # 动态创建测试用技能
    test_moves_data = {
        "序列启动器A_致命": {
            "display": {"power": 0, "pp": 10, "type": "一般", "category": "status"},
            "on_use": { "effects": [{"handler": "start_sequence", "sequence_id": "TestCombo_Kill", "initial_charges": 1}] },
            "on_follow_up": { "TestCombo_Kill": [[{"handler": "deal_damage", "options": {"power": 1000}}]] }
        },
        "序列启动器B_无害": {
            "display": {"power": 0, "pp": 10, "type": "一般", "category": "status"},
            "on_use": { "effects": [{"handler": "start_sequence", "sequence_id": "HarmlessFollowUp", "initial_charges": 1}] },
            "on_follow_up": { "HarmlessFollowUp": [[{"handler": "stat_change", "target": "self", "changes": [{"stat": "defense", "change": 1}]}]] }
        }
    }
    for name, data in test_moves_data.items():
        move_model = MoveDataModel.model_validate(data)
        game_factory._move_db[name] = move_model
        if move_model.on_follow_up:
            for seq_id, steps_raw in move_model.on_follow_up.items():
                validated_steps = [[EffectModel.model_validate(eff) for eff in step] for step in steps_raw]
                game_factory._follow_up_sequences[seq_id] = [[eff.model_dump() for eff in step] for step in validated_steps]

    player_team = [game_factory.create_pokemon("测试精灵3", 100)]
    player = player_team[0]
    move_c = game_factory.get_move_template("挑衅")
    player.skill_slots = [SkillSlot(0, move_c)]
    
    npc_team = [game_factory.create_pokemon("测试精灵", 100)]
    battle = Battle(player_team, npc_team, game_factory)

    # 关键修正：直接施加效果，而不是通过 process_turn
    player.apply_effect('sequence_slot_0', source_move='序列启动器A_致命', options={'total_charges': 1, 'charges': 1, 'source_slot_index': 0, 'sequence_id': 'TestCombo_Kill'})
    player.apply_effect('sequence_slot_1', source_move='序列启动器B_无害', options={'total_charges': 1, 'charges': 1, 'source_slot_index': 1, 'sequence_id': 'HarmlessFollowUp'})
    assert player.has_effect("sequence_slot_0") and player.has_effect("sequence_slot_1"), "测试准备阶段失败：未能成功施加两种序列效果"

    # --- Act: 执行被测行为 ---
    log3 = battle.process_turn({"type": "attack", "data": move_c})["log"]

    # --- Assert: 验证结果 ---
    assert_log_contains(log3, ["由 [序列启动器A_致命] 追击", "(NPC)测试精灵 倒下了！"])
    assert_log_not_contains(log3, ["由 [序列启动器B_无害] 追击"])
    assert player.get_effect("sequence_slot_1").data["charges"] == 1, "未触发的追击不应消耗计数器"


@pytest.mark.asyncio
async def test_scenario_9_immobilized_delayed_effect_prevents_action(game_factory: GameDataFactory):
    """
    【最终重构版】验证一个核心行为：
    延迟生效的"无法行动"状态，是否能在下一回合正确地阻止目标行动。
    """
    # --- Arrange: 准备测试数据和环境 ---
    # 定义一个带有延迟生效“无法行动”效果的技能
    game_factory._effects_db["immobilized"] = {
        "name": "无法行动", "category": "status", "status_type": "immobilization", "is_volatile": True,
        "apply_log": "陷入了 [无法行动] 状态！\n  (将从下一回合开始无法行动!)"
    }
    immobilize_move_data = {
        "禁锢之光": {
            "display": {"power": 0, "pp": 10, "type": "电", "category": "status"},
            "on_use": { "priority": 8, "effects": [{"handler": "apply_status", "status": "immobilized", "options": {"delay_activation_turns": 1}}] }
        }
    }
    game_factory._move_db["禁锢之光"] = MoveDataModel.model_validate(immobilize_move_data["禁锢之光"])

    # 创建宝可梦和战斗实例
    player_team = [game_factory.create_pokemon("测试精灵3", 100, move_names=["禁锢之光"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])]
    player_team[0].stats[Stat.SPEED] = 100 # 确保玩家先手
    npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    player, npc = battle.player_active_pokemon, battle.npc_active_pokemon

    # --- Act & Assert: 第一回合 ---
    # 玩家使用“禁锢之光”，NPC获得延迟的“无法行动”效果
    log1 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("禁锢之光")})["log"]
    
    # 验证：在这一回合，NPC仍然可以行动，因为效果尚未激活
    assert npc.has_effect("immobilized"), "NPC 应已获得'无法行动'效果"
    assert npc.get_effect("immobilized").data.get("delay_activation_turns") == 0, "延迟计数器应在回合结束时归零"
    assert_log_contains(log1, ["(NPC)测试精灵 使用了 猛烈撞击！"])

    # --- Act & Assert: 第二回合 ---
    # 玩家再次行动
    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("禁锢之光")})["log"]

    # 核心验证：在这一回合，NPC 必须“无法行动”
    # 我们验证日志中【不包含】NPC成功行动的记录，但【包含】NPC无法行动的记录
    assert_log_contains(log2, ["(NPC)测试精灵 无法行动！"])
    assert_log_not_contains(log2, ["(NPC)测试精灵 使用了 猛烈撞击！"])

@pytest.mark.asyncio
async def test_scenario_10_pp_depleted_forces_immobilized_turn(game_factory: GameDataFactory):
    player_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])]
    
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon
    
    move_name = "猛烈撞击"
    move = player.get_move_by_name(move_name)
    for _ in range(move.max_pp):
        player.use_move(move_name)
    
    assert not player.has_usable_moves()
    
    player_action = battle._create_action_from_intent(player, {"type": "attack", "data": move})
    assert player_action["type"] == "immobilized_turn"

    log = battle.process_turn({"type": "attack", "data": move})["log"]
    assert_log_contains(log, ["(玩家)测试精灵 无法行动！"])
    
    npc = battle.npc_active_pokemon
    npc_move_name = "巨焰吞噬"
    npc_move = npc.get_move_by_name(npc_move_name)
    for _ in range(npc_move.max_pp):
        npc.use_move(npc_move_name)
    assert not npc.has_usable_moves()
    
    npc_action = battle._create_npc_action(npc)
    assert npc_action["type"] == "immobilized_turn"