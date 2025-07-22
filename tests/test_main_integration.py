# tests/test_main_integration.py (最终简化版)

import pytest
from unittest.mock import MagicMock

from astrbot_plugin_hapemxg_roco1.main import PokemonBattlePlugin

@pytest.fixture
def plugin_instance_integration(mocker) -> PokemonBattlePlugin:
    """
    【最终版Fixture】创建一个加载【真实代码】的插件实例，并精确模拟所有外部依赖。
    """
    def config_get_side_effect(key):
        if key == 'npc_1_name': return '测试精灵2'
        if key == 'npc_1_moves': return ['冥暗诅咒', '巨焰吞噬']
        if key == 'npc_2_name': return '测试精灵3'
        if key == 'npc_2_moves': return []
        if key.startswith('npc_'): return None
        return MagicMock()

    mock_config = mocker.Mock()
    mock_config.get.side_effect = config_get_side_effect
    mock_context = mocker.Mock()

    plugin = PokemonBattlePlugin(context=mock_context, config=mock_config)
    return plugin

@pytest.mark.asyncio
async def test_plugin_initialization_with_mock_config(plugin_instance_integration: PokemonBattlePlugin):
    """
    【核心集成测试】
    验证插件能否在模拟配置下成功实例化，并正确加载NPC配置。
    """
    plugin = plugin_instance_integration
    assert plugin is not None
    assert plugin.factory is not None, "插件的 GameDataFactory 未能成功加载"
    assert len(plugin.npc_team_config_list) == 2, "插件未能正确解析模拟的NPC配置"
    assert plugin.npc_team_config_list[0]['name'] == '测试精灵2'
    assert plugin.npc_team_config_list[1]['moves'] == []