# tests/test_pokemon.py
import pytest
from pathlib import Path
from astrbot_plugin_hapemxg_roco1.battle_logic.factory import GameDataFactory
from astrbot_plugin_hapemxg_roco1.battle_logic.pokemon import Pokemon
from astrbot_plugin_hapemxg_roco1.battle_logic.constants import Stat
from astrbot_plugin_hapemxg_roco1.battle_logic.components import StatStageComponent

@pytest.fixture(scope="module")
def game_factory() -> GameDataFactory:
    plugin_root = Path(__file__).parent.parent 
    test_data_path = plugin_root / "tests" / "test_data"
    if not test_data_path.exists():
        test_data_path = plugin_root / "data"
        if not test_data_path.exists():
             pytest.fail(f"测试数据目录 'tests/test_data' 或 'data' 未找到")
    return GameDataFactory(test_data_path)

@pytest.mark.asyncio
async def test_pokemon_creation(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    assert p is not None and p.name == "测试精灵" and p.level == 50 and p.max_hp > 0 and p.current_hp == p.max_hp and not p.is_fainted()

@pytest.mark.asyncio
async def test_pokemon_take_damage(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    hp = p.current_hp
    p.take_damage(20)
    assert p.current_hp == hp - 20 and not p.is_fainted()

@pytest.mark.asyncio
async def test_pokemon_faints_on_lethal_damage(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    p.take_damage(p.max_hp + 10)
    assert p.current_hp == 0 and p.is_fainted()

@pytest.mark.asyncio
async def test_stat_stage_cannot_exceed_limit(game_factory: GameDataFactory):
    """【已修复】本测试已更新，以使用正确的Aura/Component API进行断言。"""
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    
    # 步骤1: 手动将攻击等级提升到+6
    # 通过直接向宝可梦的Aura中添加一个组件来模拟这个状态
    p.aura.add_component(StatStageComponent(Stat.ATTACK, 6))
    
    # 步骤2: 尝试再次提升攻击等级
    success, message = p.apply_stat_change(Stat.ATTACK, 1)
    
    # 步骤3: 断言结果
    assert not success, "当能力已达+6时，apply_stat_change应返回False"
    assert "已无法再提升" in message, "应返回无法提升的提示信息"
    
    # 步骤4: 验证最终的能力等级总和仍然是6
    # 通过遍历Aura中所有相关的组件并求和来验证最终状态
    total_attack_stage = sum(c.change for c in p.aura.get_components(StatStageComponent) if c.stat == Stat.ATTACK)
    assert total_attack_stage == 6, "攻击等级总和应保持在+6"