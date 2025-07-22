# tests/test_pokemon.py
import pytest
from pathlib import Path
from astrbot_plugin_hapemxg_roco1.battle_logic.factory import GameDataFactory
from astrbot_plugin_hapemxg_roco1.battle_logic.pokemon import Pokemon
from astrbot_plugin_hapemxg_roco1.battle_logic.constants import Stat

@pytest.fixture(scope="module")
def game_factory() -> GameDataFactory:
    plugin_root = Path(__file__).parent.parent 
    test_data_path = plugin_root / "tests" / "test_data"
    if not test_data_path.exists(): pytest.fail(f"测试数据目录未找到: {test_data_path}")
    return GameDataFactory(test_data_path)

@pytest.mark.asyncio
async def test_pokemon_creation(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    assert p is not None and p.name == "测试精灵" and p.level == 50 and p.max_hp > 0 and p.current_hp == p.max_hp and not p.is_fainted()

@pytest.mark.asyncio
async def test_pokemon_take_damage(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    hp = p.current_hp; p.take_damage(20); assert p.current_hp == hp - 20 and not p.is_fainted()

@pytest.mark.asyncio
async def test_pokemon_faints_on_lethal_damage(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    p.take_damage(p.max_hp + 10); assert p.current_hp == 0 and p.is_fainted()

@pytest.mark.asyncio
async def test_stat_stage_cannot_exceed_limit(game_factory: GameDataFactory):
    p = game_factory.create_pokemon(name="测试精灵", level=50)
    p.stat_stages[Stat.ATTACK] = 6
    success, message = p.apply_stat_change(Stat.ATTACK, 1)
    # 【核心修复】调整断言以匹配 pokemon.py 中的实际返回文本
    assert not success, "当能力已达+6时，应返回False"
    assert p.stat_stages[Stat.ATTACK] == 6, "攻击等级应保持在+6"
    assert "已无法再提升" in message, "应返回无法提升的提示信息"