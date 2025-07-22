# astrbot_plugin_hapemxg_roco1/main.py

from pathlib import Path
from typing import Dict, Optional, Any, List, Callable

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .service import GameService, ServiceResult
from .battle_logic.factory import GameDataFactory

@register("PokemonBattle", "YourName", "宝可梦对战模拟器", "24.0.0-15-GOLD-MASTER")
class PokemonBattlePlugin(Star):
    """
    宝可梦对战模拟器插件。
    该插件实现了完整的宝可梦选择、配置和对战逻辑。
    
    架构设计:
    - Main (本文件): 插件入口，负责处理AstrBot指令，并将业务逻辑委托给GameService。采用命令执行器模式
      (`_execute_command`)来消除重复代码，保持指令处理函数整洁。
    - Service: 应用服务层，处理会话管理、业务流程编排和UI生成。是连接各层的桥梁。
    - UI: 表现层，负责生成所有用户可见的消息文本，与核心逻辑完全解耦。
    - Battle_Logic (领域层): 包含战斗、宝可梦、技能等核心领域模型和规则，与AstrBot框架无关，
      具有高度的可移植性和可测试性。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        """
        初始化插件，加载数据，并准备服务。
        """
        super().__init__(context)
        self.factory: Optional[GameDataFactory] = None
        self.service: Optional[GameService] = None
        # 【修复】将 npc_team_config_list 声明为实例属性，确保其生命周期与插件实例一致。
        self.npc_team_config_list: List[Dict[str, Any]] = []

        try:
            # 1. 初始化数据工厂
            data_path = Path(__file__).parent / "data"
            self.factory = GameDataFactory(data_path)
            
            # 2. 解析NPC配置并赋值给实例属性
            self.npc_team_config_list = self._parse_npc_config(config)
            
            # 3. 初始化核心服务，使用实例属性进行配置
            self.service = GameService(self.factory, self.npc_team_config_list)
            
            logger.info("宝可梦插件服务启动成功。")
        except Exception as e:
            # 如果任何步骤失败，记录详细错误并阻止插件服务启动
            logger.error(f"宝可梦插件因初始化失败而无法启动: {e}", exc_info=True)
            # 将service置为None，以便后续指令能够安全地失败并提示用户
            self.service = None

    def _parse_npc_config(self, config: AstrBotConfig) -> List[Dict[str, Any]]:
        """
        从插件配置中解析NPC队伍信息。
        这是一个独立的辅助方法，以保持 __init__ 的整洁。

        Args:
            config: AstrBot的配置对象。

        Returns:
            一个包含NPC宝可梦配置字典的列表。
        """
        npc_configs: List[Dict[str, Any]] = []
        # 最多支持6个NPC宝可梦配置
        for i in range(1, 7):
            pokemon_name = config.get(f"npc_{i}_name")
            if pokemon_name and isinstance(pokemon_name, str) and pokemon_name.strip():
                moves = config.get(f"npc_{i}_moves")
                npc_configs.append({
                    "name": pokemon_name.strip(),
                    "moves": moves if isinstance(moves, list) else []
                })
        
        if not npc_configs:
            logger.warning("宝可梦插件：NPC队伍为空，请检查后台配置。")
        else:
            logger.info(f"宝可梦插件：成功加载 {len(npc_configs)} 名NPC宝可梦配置。")
        return npc_configs

    async def _handle_service_call(self, event: AstrMessageEvent, result: ServiceResult):
        """
        统一处理来自GameService的ServiceResult，并生成回复。
        """
        if not result.success and result.log_level:
            log_func = getattr(logger, result.log_level, logger.info)
            log_func(f"宝可梦插件业务逻辑失败: {result.message} (用户: {event.get_user_id()})")
        yield event.plain_result(result.message)

    async def _execute_command(
        self, 
        event: AstrMessageEvent, 
        service_method: Callable[..., ServiceResult], 
        *args: Any, 
        **kwargs: Any
    ):
        """
        【核心重构】命令执行器，封装了所有指令的通用处理逻辑。
        
        它负责：
        1. 检查服务是否可用，如果不可用则返回统一的错误提示。
        2. 调用指定的service方法并传递参数。
        3. 将返回的ServiceResult通过_handle_service_call转换为最终回复。
        
        这极大地简化了每个指令处理函数的代码，遵循了DRY原则。

        Args:
            event: 消息事件对象。
            service_method: 要调用的GameService中的方法。
            *args: 传递给service_method的位置参数。
            **kwargs: 传递给service_method的关键字参数。
        """
        if not self.service:
            yield event.plain_result("错误：宝可梦插件未成功初始化，请检查后台日志。")
            return

        result = service_method(*args, **kwargs)
        
        async for msg in self._handle_service_call(event, result):
            yield msg

    # --- 指令处理函数 (已重构，代码简洁清晰) ---

    @filter.command_group("battle")
    async def battle_group(self, event: AstrMessageEvent):
        """处理无效的 /battle 子命令，提供帮助信息。"""
        yield event.plain_result("无效的子命令。可用: start, add, setmove, ready, flee, switch, attack")

    @battle_group.command("start")
    async def start_selection(self, event: AstrMessageEvent):
        """开始一个新的宝可梦队伍选择会话。"""
        async for msg in self._execute_command(event, self.service.start_new_selection, event.get_session_id()):
            yield msg
    
    @battle_group.command("add")
    async def add_to_team(self, event: AstrMessageEvent):
        """向队伍中添加一个或多个宝可梦。"""
        parts = event.message_str.split()
        if len(parts) < 3: 
            yield event.plain_result("格式错误。正确用法: /battle add <名字1> [名字2] ..."); return
        
        async for msg in self._execute_command(
            event, self.service.add_pokemon_to_team, event.get_session_id(), parts[2:]
        ):
            yield msg

    @battle_group.command("setmove", args=(3,))
    async def set_move(self, event: AstrMessageEvent, p_name: str, f_move: str, l_move: str):
        """为队伍中的宝可梦更换技能。"""
        async for msg in self._execute_command(
            event, self.service.set_pokemon_move, event.get_session_id(), p_name, f_move, l_move
        ):
            yield msg

    @battle_group.command("ready", args=(1,))
    async def ready_battle(self, event: AstrMessageEvent, starter: str):
        """完成队伍选择，指定首发并开始战斗。"""
        async for msg in self._execute_command(
            event, self.service.ready_and_start_battle, event.get_session_id(), starter
        ):
            yield msg

    @battle_group.command("flee")
    async def flee_battle(self, event: AstrMessageEvent):
        """从战斗中逃跑。"""
        async for msg in self._execute_command(event, self.service.flee_battle, event.get_session_id()):
            yield msg

    @filter.command("attack", args=(1,))
    async def attack(self, event: AstrMessageEvent, move: str):
        """在战斗中发动攻击。"""
        async for msg in self._execute_command(event, self.service.execute_attack, event.get_session_id(), move):
            yield msg

    @battle_group.command("switch")
    async def switch_pokemon(self, event: AstrMessageEvent, target: Optional[str] = None):
        """在战斗中切换宝可梦，或查看队伍状态。"""
        async for msg in self._execute_command(event, self.service.execute_switch, event.get_session_id(), target):
            yield msg