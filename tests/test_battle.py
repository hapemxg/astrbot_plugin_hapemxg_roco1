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
from astrbot_plugin_hapemxg_roco1.battle_logic.components import StatStageComponent

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
    # Arrange
    player_team = [game_factory.create_pokemon("测试精灵4", 100, move_names=["龙威"])]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])]
    player_team[0].stats[Stat.SPEED] = 100
    npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    npc = battle.npc_active_pokemon
    
    # Pre-condition: 先给NPC施加一个B类状态（麻醉）
    npc.apply_effect("anesthesia")
    assert npc.has_effect("anesthesia"), "测试前置条件失败：未能成功施加麻醉状态"

    # Act: 玩家使用“龙威”，此技能会施加B类状态“恐惧”
    log1 = battle.process_turn({"type": "attack", "data": battle.player_active_pokemon.get_move_by_name("龙威")})["log"]
    
    # Assert
    # 1. 验证最终状态：
    assert npc.has_effect("fear"), "断言失败：NPC最终应处于恐惧状态"
    assert not npc.has_effect("anesthesia"), "断言失败：麻醉状态应已被恐惧正确顶替"
    
    # 2. 验证过程日志：
    assert_log_contains(log1, [
        "的 [麻醉] 状态解除了。", # 期望日志1: 系统应播报旧状态被解除。这是 apply_effect 顶替逻辑的一部分。
        "陷入了 [恐惧]！",      # 期望日志2: 系统应播报新状态已施加。
        "因 [恐惧] 而无法行动！" # 期望日志3: 在NPC自己的小回合开始前，_check_can_act会检查恐惧状态，并因on_clear_fail施加畏缩，最终导致此日志。
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
    # Part A (无变化)
    player_A = game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])
    npc_A = game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])
    battle_A = Battle([player_A], [npc_A], game_factory)
    initial_pp_A = npc_A.get_current_pp("巨焰吞噬")
    battle_A.process_turn({"type": "attack", "data": player_A.get_move_by_name("猛烈撞击")})
    assert npc_A.get_current_pp("巨焰吞噬") == initial_pp_A - 1

    # Part B
    player_B = game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])
    npc_B = game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])
    battle_B = Battle([player_B], [npc_B], game_factory)
    
    # 【核心修正】使用我们最终确认的、有效的状态ID "anesthesia"
    npc_B.apply_effect("anesthesia")
    initial_pp_B = npc_B.get_current_pp("巨焰吞噬")
    
    # 通过monkeypatch强制触发麻痹的“无法行动”效果
    monkeypatch.setattr(random, "random", lambda: 0.01) # 确保 random() < 0.5
    
    log = battle_B.process_turn({"type": "attack", "data": player_B.get_move_by_name("猛烈撞击")})["log"]
    
    # Assert
    # 1. 验证日志：
    # 期望日志: 在NPC行动前，_check_can_act 会检查麻醉状态，并根据 immobility_chance 判定无法行动。
    assert_log_contains(log, ["因 [麻醉] 而全身麻痹，无法行动！"])
    # 2. 验证PP：
    # 期望结果: 因为行动被 _check_can_act 阻止，后续的 _execute_action_core 不会执行，因此不会有PP消耗。
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
async def test_scenario_9_immobilized_is_decoupled_from_flinch(game_factory: GameDataFactory):
    # Arrange: 准备一个施加纯粹“无法行动”的技能
    immobilize_move_data = {
        "禁锢之光": {
            "display": {"power": 0, "pp": 10, "type": "电", "category": "status"},
            "on_use": { "effects": [{"handler": "apply_status", "status": "immobilized"}] }
        }
    }
    game_factory._move_db["禁锢之光"] = MoveDataModel.model_validate(immobilize_move_data["禁锢之光"])
    # 确保 immobilize 效果存在
    game_factory._effects_db["immobilized"] = {
        "name": "无法行动", "category": "status", "status_type": "immobilization", "is_volatile": True,
        "apply_log": "陷入了 [无法行动] 状态！(效果将在下回合生效)"
    }

    player_team = [game_factory.create_pokemon("测试精灵3", 100, move_names=["禁锢之光"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])]
    player_team[0].stats[Stat.SPEED] = 100 # 玩家先手
    npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    player, npc = battle.player_active_pokemon, battle.npc_active_pokemon

    # --- Act & Assert: 第一回合 ---
    log1 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("禁锢之光")})["log"]
    
    # 1. 验证状态和日志
    assert npc.has_effect("immobilized"), "断言失败：NPC应已获得'无法行动'效果"
    assert_log_contains(log1, ["陷入了 [无法行动] 状态！"])
    
    # 2. 验证当回合行为
    # 期望结果: 因为“无法行动”和“畏缩”已彻底解耦，纯粹的“无法行动”效果不应阻止当回合的后手行动。
    assert_log_contains(log1, ["(NPC)测试精灵 使用了 猛烈撞击！"])

    # --- Act & Assert: 第二回合 ---
    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("禁锢之光")})["log"]

    # 3. 验证下一回合行为
    # 期望结果: 在新回合开始时，battle._create_action_from_intent 会检查到NPC身上有一个“非新获得”的“无法行动”状态，从而阻止其行动。
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
    
@pytest.mark.asyncio
async def test_shengjie_purge_and_reset_works(game_factory: GameDataFactory):
    """测试“圣洁”能否正确净化异常状态和重置负面能力。"""
    # Arrange
    player = game_factory.create_pokemon("测试精灵", 100, move_names=["圣洁"])
    npc = game_factory.create_pokemon("测试精灵2", 100, move_names=["金属噪音"]) # 金属噪音降特防
    battle = Battle([player], [npc], game_factory)

    # 1. 先给玩家施加中毒和负面能力
    player.apply_effect("poison")
    player.aura.add_component(StatStageComponent(Stat.ATTACK, -2))
    assert player.has_effect("poison"), "前置条件失败：未能施加中毒"
    total_attack_stage = sum(c.change for c in player.aura.get_components(StatStageComponent) if c.stat == Stat.ATTACK)
    assert total_attack_stage == -2, "前置条件失败：未能施加负面能力"

    # Act
    log = battle.process_turn({"type": "attack", "data": player.get_move_by_name("圣洁")})["log"]

    # Assert
    assert not player.has_effect("poison"), "断言失败：“圣洁”未能净化中毒状态"
    total_attack_stage_after = sum(c.change for c in player.aura.get_components(StatStageComponent) if c.stat == Stat.ATTACK)
    assert total_attack_stage_after == 0, "断言失败：“圣洁”未能重置负面能力"
    
    assert_log_contains(log, [
        "身上的所有异常状态都被净化了！",
        "被削弱的能力 (攻击) 恢复到了正常水平！",
        "被圣洁的光芒笼罩，获得了闪避能力！"
    ])

@pytest.mark.asyncio
async def test_shengjie_initial_evasion_works(game_factory: GameDataFactory):
    """测试“圣洁”第一回合获得的闪避状态能否生效。"""
    # Arrange
    player = game_factory.create_pokemon("测试精灵", 100, move_names=["圣洁"])
    npc = game_factory.create_pokemon("测试精灵2", 100, move_names=["猛烈撞击"])
    # 确保NPC后手，以便在下一回合攻击
    player.stats[Stat.SPEED] = 100
    npc.stats[Stat.SPEED] = 50
    battle = Battle([player], [npc], game_factory)

    # Act (Turn 1): 玩家使用圣洁
    battle.process_turn({"type": "attack", "data": player.get_move_by_name("圣洁")})
    assert player.has_effect("shengjie_evasion")

    # Act (Turn 2): NPC攻击
    log = battle.process_turn({"type": "attack", "data": player.get_move_by_name("圣洁")})["log"]
    
    # Assert: NPC的攻击应该落空
    assert_log_contains(log, ["(NPC)测试精灵2 使用了 猛烈撞击！", "但攻击落空了！"])
    assert_log_not_contains(log, ["造成了"])

@pytest.mark.asyncio
async def test_shengjie_sequence_removes_evasion(game_factory: GameDataFactory):
    """测试“圣洁”在正常情况下，第二回合追击能否移除闪避。"""
    # Arrange
    player = game_factory.create_pokemon("测试精灵", 100, move_names=["圣洁", "猛烈撞击"])
    npc = game_factory.create_pokemon("测试精灵2", 100, move_names=["猛烈撞击"])
    battle = Battle([player], [npc], game_factory)

    # Act (Turn 1): 玩家使用圣洁
    battle.process_turn({"type": "attack", "data": player.get_move_by_name("圣洁")})
    assert player.has_effect("shengjie_evasion")

    # Act (Turn 2): 玩家使用其他技能，触发追击
    log = battle.process_turn({"type": "attack", "data": player.get_move_by_name("猛烈撞击")})["log"]
    
    # Assert
    assert_log_contains(log, ["由 [圣洁] 追击", "的圣洁光芒消散了。"])
    assert not player.has_effect("shengjie_evasion"), "断言失败：第二回合追击后，圣洁闪避应被移除"

@pytest.mark.asyncio
async def test_shengjie_kill_preserves_evasion_for_next_turn(game_factory: GameDataFactory):
    """【核心战术测试】验证通过击杀中断回合，能否保留闪避状态到下一回合，并闪避优先技能。"""
    # --- Arrange ---
    player = game_factory.create_pokemon("测试精灵", 100, move_names=["圣洁", "星之雨", "魔法增效"])
    # 准备一个会被击杀的NPC和它的替补
    npc_to_be_killed = game_factory.create_pokemon("测试精灵2", 100)
    npc_replacement = game_factory.create_pokemon("测试精灵3", 100, move_names=["速度打击"]) # 替补带有优先技能
    
    battle = Battle([player], [npc_to_be_killed, npc_replacement], game_factory)
    
    # 确保玩家能一击必杀
    npc_to_be_killed.take_damage(npc_to_be_killed.max_hp - 1)
    assert npc_to_be_killed.current_hp == 1, "前置条件失败：未能将NPC血量设为1"
    
    # 确保NPC的替补速度更快，但玩家的技能有更高优先级
    player.stats[Stat.SPEED] = 100
    npc_replacement.stats[Stat.SPEED] = 200

    # --- Turn 1: 玩家使用“圣洁” ---
    log1 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("圣洁")})["log"]
    assert player.has_effect("shengjie_evasion"), "第一回合失败：未能获得圣洁闪避"
    assert_log_contains(log1, ["获得了闪避能力"])
    
    # --- Turn 2: 玩家使用“星之雨”击杀NPC ---
    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("星之雨")})["log"]
    
    # 验证回合是否被正确中断
    assert npc_to_be_killed.is_fainted(), "第二回合失败：未能击杀NPC"
    assert battle.npc_active_pokemon is npc_replacement, "第二回合失败：NPC替补未能上场"
    assert_log_contains(log2, ["(NPC)测试精灵2 倒下了！", "(NPC) 派出了新的宝可梦：测试精灵3！"])
    
    # 核心断言：验证追击效果未触发，闪避状态被保留
    assert_log_not_contains(log2, ["由 [圣洁] 追击"])
    assert player.has_effect("shengjie_evasion"), "核心断言失败：击杀后，圣洁闪避状态应被保留！"

    # --- Turn 3: 对方替补先手攻击，我方后手增效 ---
    log3 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("魔法增效")})["log"]
    
    # 最终断言：验证NPC的优先攻击是否因闪避而落空
    assert_log_contains(log3, [
        "(NPC)测试精灵3 使用了 速度打击！", # 对方先手
        "但攻击落空了！",             # 攻击落空
        "(玩家)测试精灵 使用了 魔法增效！"  # 我方后手成功
    ])
    assert_log_not_contains(log3, ["对 (玩家)测试精灵 造成了"])