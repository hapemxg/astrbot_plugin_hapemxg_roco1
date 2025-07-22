# tests/test_battle.py
import pytest
import random
from pathlib import Path
from copy import deepcopy

from astrbot_plugin_hapemxg_roco1.battle_logic import battle as battle_module
from astrbot_plugin_hapemxg_roco1.battle_logic.battle import Battle
from astrbot_plugin_hapemxg_roco1.battle_logic.pokemon import Pokemon, SkillSlot
from astrbot_plugin_hapemxg_roco1.battle_logic.factory import GameDataFactory
from astrbot_plugin_hapemxg_roco1.battle_logic.constants import Stat
# 【新增】导入Pydantic模型，用于动态创建和验证技能数据
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
    return GameDataFactory(test_data_path)

def assert_log_contains(log: str, expected: list[str]):
    for sub in expected: assert sub in log, f"日志未找到期望内容: '{sub}'"

def assert_log_not_contains(log: str, unexpected: list[str]):
    for sub in unexpected: assert sub not in log, f"日志中出现了不应有的内容: '{sub}'"

# --- 测试剧本 (最终的、艺术品级的版本) ---


@pytest.mark.asyncio
async def test_scenario_1_curse_is_volatile_on_switch(game_factory: GameDataFactory):
    """剧本1：验证“诅咒”效果的“挥发性”"""
    player_team = [
        game_factory.create_pokemon("初始精灵-test", 100),
        game_factory.create_pokemon("替换精灵-test", 100)
    ]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["冥暗诅咒"])]
    player_team[0].stats[Stat.SPEED] = 100; npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    pokemon_to_be_cursed, pokemon_to_switch_in = player_team[0], player_team[1]

    player_action = {"type": "attack", "data": pokemon_to_be_cursed.get_move_by_name("速度打击")}
    battle.process_turn(player_action)
    assert pokemon_to_be_cursed.has_effect("curse")

    battle.process_turn({"type": "switch", "data": pokemon_to_switch_in})
    assert battle.player_active_pokemon is pokemon_to_switch_in
    assert not pokemon_to_be_cursed.has_effect("curse")


@pytest.mark.asyncio
async def test_scenario_2_poison_damage_log_timing(game_factory: GameDataFactory):
    """剧本2：验证“中毒”伤害的回合末日志结算时机"""
    # 注意: moves.json 中没有'剧毒'，我们使用'臭鸡蛋'来施加'poison'
    player_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["臭鸡蛋"])]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])]
    player_team[0].stats[Stat.SPEED] = 100; npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    
    log1 = battle.process_turn({"type": "attack", "data": battle.player_active_pokemon.get_move_by_name("臭鸡蛋")})["log"]
    
    assert battle.npc_active_pokemon.has_effect("poison")
    assert_log_contains(log1, [
        "陷入了 [中毒] 状态！", # 确认日志文本
        "(NPC)测试精灵2 使用了 巨焰吞噬！",
        "因 [中毒] 受到了",
    ])


@pytest.mark.asyncio
async def test_scenario_3_fear_replaces_paralysis_and_triggers_flinch(game_factory: GameDataFactory):
    """剧本3：验证“恐惧”替换“麻痹”并触发“畏缩”的机制"""
    player_team = [game_factory.create_pokemon("测试精灵4", 100, move_names=["龙威"])]
    npc_team = [game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])]
    player_team[0].stats[Stat.SPEED] = 100; npc_team[0].stats[Stat.SPEED] = 50
    battle = Battle(player_team, npc_team, game_factory)
    npc = battle.npc_active_pokemon
    
    npc.apply_effect("paralysis")
    assert npc.has_effect("paralysis")

    log1 = battle.process_turn({"type": "attack", "data": battle.player_active_pokemon.get_move_by_name("龙威")})["log"]
    
    assert npc.has_effect("fear")
    assert not npc.has_effect("paralysis")
    
    # 【核心修复】将期望的日志文本从“陷入了...”改为“获得了...”，与 pokemon.py 的实现保持一致
    assert_log_contains(log1, [
        "的 [恐惧] 效果替换了 [麻痹]！",
        "获得了 [畏缩] 效果！",          # <-- 已校准
        "(NPC)测试精灵2 畏缩了，无法行动！"
    ])
    
    assert not npc.has_effect("flinch")


# tests/test_battle.py
# ... (其他所有测试函数和辅助代码都保持不变) ...

@pytest.mark.asyncio
async def test_scenario_4_sequence_refresh_is_precise(game_factory: GameDataFactory):
    """
    剧本4：验证序列效果的【精确】刷新
    
    目的：
      确保使用一个连击技能，只会刷新它自己对应的序列效果，
      而不会错误地影响到另一个并存的序列效果。
    """
    player_team = [game_factory.create_pokemon("测试精灵3", 100, move_names=["测试连击1", "猛烈撞击", "龙之连舞", "破土之力"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100)]
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon

    # 第1回合：启动“测试连击1” (2层)
    battle.process_turn({"type": "attack", "data": player.get_move_by_name("测试连击1")})
    assert player.get_effect("sequence_slot_0").data.get("charges") == 2

    # 第2回合：使用“龙之连舞”。此时，“测试连击1”会触发第一次追击
    battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})
    assert player.get_effect("sequence_slot_0").data.get("charges") == 1, "测试连击1应消耗一层，剩余1层"
    assert player.get_effect("sequence_slot_2").data.get("charges") == 2, "龙之连舞被施加，拥有2层"

    # 第3回合：再次使用“龙之连舞”。此时，“测试连击1”会触发第二次追击并结束，“龙之连舞”则会刷新
    log = battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})["log"]

    # 断言：
    # 1. “测试连击1”的第二次追击发生，并且序列结束
    assert "由 [测试连击1] 追击" in log
    assert "的 [测试连击1] 序列结束了" in log
    assert not player.has_effect("sequence_slot_0"), "测试连击1序列应已结束并被移除"
    
    # 2. “龙之连舞”的序列被刷新，层数重置为2
    assert player.get_effect("sequence_slot_2").data.get("charges") == 2, "龙之连舞序列应被刷新"


@pytest.mark.asyncio
async def test_scenario_5_sequence_execution_order_and_initial_hit(game_factory: GameDataFactory):
    """
    剧本5：验证序列的【初始伤害】与【追击顺序】
    
    目的：
      1. 验证连击技能在【使用回合】，只造成初始伤害，不触发追击。
      2. 验证在后续回合，追击严格按技能槽顺序结算。
    """
    player_team = [game_factory.create_pokemon("测试精灵3", 100, move_names=["测试连击1", "猛烈撞击", "龙之连舞", "破土之力"])]
    npc_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])]
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon

    # 第1回合：使用龙之连舞(3号槽)。预期：只造成初始伤害，不追击
    log1 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})["log"]
    assert "由 [龙之连舞] 追击" not in log1, "连击技能在启动回合不应触发追击"
    assert player.get_effect("sequence_slot_2") is not None

    # 第2回合：使用测试连击1(1号槽)。预期：龙之连舞触发第1次追击，测试连击1只造成初始伤害
    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("测试连击1")})["log"]
    assert "由 [龙之连舞] 追击" in log2, "龙之连舞应在第2回合触发追击"
    assert "由 [测试连击1] 追击" not in log2, "测试连击1在启动回合不应追击"
    assert player.get_effect("sequence_slot_0") is not None
    assert player.get_effect("sequence_slot_2").data.get("charges") == 1 # 龙之连舞消耗1层

    # 第3回合：使用普通攻击，触发所有追击
    log3 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("猛烈撞击")})["log"]
    combo1_log_index = log3.find("由 [测试连击1] 追击")
    dd_log_index = log3.find("由 [龙之连舞] 追击")
    assert combo1_log_index != -1 and dd_log_index != -1, "两个追击都应被触发"
    assert combo1_log_index < dd_log_index, "追击结算必须严格按照技能槽顺序 (0号槽优先于2号槽)"


@pytest.mark.asyncio
async def test_scenario_6_pp_consumption_logic(game_factory: GameDataFactory, monkeypatch):
    """剧本6 (原5)：验证PP消耗的正确逻辑"""
    # 场景A
    player_A = game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])
    npc_A = game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])
    battle_A = Battle([player_A], [npc_A], game_factory)
    npc_move_A = npc_A.get_move_by_name("巨焰吞噬"); initial_pp_A = npc_move_A.current_pp
    battle_A.process_turn({"type": "attack", "data": player_A.get_move_by_name("猛烈撞击")})
    assert npc_move_A.current_pp == initial_pp_A - 1

    # 场景B
    player_B = game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])
    npc_B = game_factory.create_pokemon("测试精灵2", 100, move_names=["巨焰吞噬"])
    npc_B.apply_effect("paralysis")
    battle_B = Battle([player_B], [npc_B], game_factory)
    npc_move_B = npc_B.get_move_by_name("巨焰吞噬"); initial_pp_B = npc_move_B.current_pp
    
    monkeypatch.setattr(battle_module.random, "random", lambda: 0.01)
    
    log = battle_B.process_turn({"type": "attack", "data": player_B.get_move_by_name("猛烈撞击")})["log"]
    
    assert_log_contains(log, ["全身麻痹，无法行动！"])
    assert npc_move_B.current_pp == initial_pp_B
    
    # tests/test_battle.py
# ... (所有其他测试保持不变) ...

@pytest.mark.asyncio
async def test_scenario_7_sequence_carries_over_after_kill(game_factory: GameDataFactory):
    """剧本7：验证序列追击在击倒目标后，能延续到下一回合对新目标生效"""
    player_team = [game_factory.create_pokemon("测试精灵4", 100, move_names=["龙之连舞", "速度打击"])]
    npc_team = [
        game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"]),
        game_factory.create_pokemon("测试精灵2", 100, move_names=["猛烈撞击"])
    ]
    npc_team[0].current_hp = 1
    battle = Battle(player_team, npc_team, game_factory)
    player = battle.player_active_pokemon
    
    # 第1回合：使用龙之连舞。初始伤害就击倒了第一个NPC。
    log1 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("龙之连舞")})["log"]
    assert "测试精灵 倒下了！" in log1
    assert "由 [龙之连舞] 追击" not in log1, "启动回合不追击"
    assert battle.npc_active_pokemon is npc_team[1], "NPC应派出第二只宝可梦"
    
    dragon_dance_slot = next(slot for slot in player.skill_slots if slot.move.name == "龙之连舞")
    sequence_effect_id = f"sequence_slot_{dragon_dance_slot.index}"
    assert player.get_effect(sequence_effect_id).data.get("charges") == 2, "序列层数应保持为2，因为还未追击"

    # 第2回合：使用普通攻击，现在应该触发第1次追击
    log2 = battle.process_turn({"type": "attack", "data": player.get_move_by_name("速度打击")})["log"]
    assert "由 [龙之连舞] 追击" in log2, "追击应在下一回合对新目标生效"
    assert player.get_effect(sequence_effect_id).data.get("charges") == 1, "追击一次后，层数应减为1"
    

# tests/test_battle.py

# ... (所有其他 import 和辅助函数保持不变) ...

@pytest.mark.asyncio
async def test_scenario_8_sequence_chain_interrupt_on_kill(game_factory: GameDataFactory, monkeypatch):
    """
    剧本8：验证追击链条在目标被击倒时会中止
    """
    # --- 步骤1: 动态创建技能 ---
    test_moves_data = {
        "序列启动器A_致命": {
            "display": {"power": 0, "pp": 10, "type": "一般", "category": "status"},
            "on_use": { "effects": [{"handler": "start_sequence", "sequence_id": "TestCombo_Kill", "initial_charges": 1}] },
            "on_follow_up": { "TestCombo_Kill": [[{"handler": "deal_damage", "options": {"power": 100, "category": "physical"}}]] }
        },
        "序列启动器B_无害": {
            "display": {"power": 0, "pp": 10, "type": "一般", "category": "status"},
            "on_use": { "effects": [{"handler": "start_sequence", "sequence_id": "HarmlessFollowUp", "initial_charges": 1}] },
            "on_follow_up": { "HarmlessFollowUp": [[{"handler": "stat_change", "target": "self", "changes": [{"stat": "defense", "change": 1}]}]] }
        }
    }
    
    # 动态加载技能到 factory
    for name, data in test_moves_data.items():
        move_model = MoveDataModel.model_validate(data)
        # 【修复核心】确保你正在修改正确的、带下划线的属性 `_move_db`
        game_factory._move_db[name] = move_model
        
        if move_model.on_follow_up:
            for seq_id, steps_raw in move_model.on_follow_up.items():
                game_factory._follow_up_sequences[seq_id] = [[eff.model_dump() for eff in step] for step in steps_raw]

    # --- 步骤2: 构建测试场景 ---
    # ... (monkeypatch 保持不变) ...

    player_team = [game_factory.create_pokemon("测试精灵3", 100)]
    player = player_team[0]
    
    # 首先获取 Move 对象，并断言它们不是 None，确保加载成功
    move_a = game_factory.get_move_template("序列启动器A_致命")
    move_b = game_factory.get_move_template("序列启动器B_无害")
    assert move_a is not None, "测试技能'序列启动器A_致命'未能从工厂加载"
    assert move_b is not None, "测试技能'序列启动器B_无害'未能从工厂加载"

    player.skill_slots = [
        SkillSlot(index=0, move=move_a),
        SkillSlot(index=1, move=move_b),
    ]

    npc_team = [game_factory.create_pokemon("测试精灵", 100, move_names=["猛烈撞击"])]
    npc_team[0].current_hp = 15
    battle = Battle(player_team, npc_team, game_factory)
    
    # --- 步骤3: 执行并验证 ---
    battle.process_turn({"type": "attack", "data": move_a})
    result_turn_2 = battle.process_turn({"type": "attack", "data": move_b})
    log_turn_2 = result_turn_2["log"]

    # 断言：
    assert "由 [序列启动器A_致命] 追击" in log_turn_2
    assert "(NPC)测试精灵 倒下了！" in log_turn_2
    assert "由 [序列启动器B_无害] 追击" not in log_turn_2