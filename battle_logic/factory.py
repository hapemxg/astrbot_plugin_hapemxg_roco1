# battle_logic/factory.py
import json
from pathlib import Path
from typing import Dict, Optional, List, Any
from copy import deepcopy 

from astrbot.api import logger
from pydantic import ValidationError

from .pokemon import Pokemon
from .move import Move
from .data_models import MoveDataModel, PokemonDataModel

class GameDataFactory:
    """
    游戏数据工厂，负责从JSON文件加载、校验并提供所有游戏核心数据。
    这是连接数据层和领域逻辑的唯一入口，确保了数据的集中管理和一致性。
    """
    def __init__(self, data_path: Path):
        """
        初始化工厂实例。

        Args:
            data_path: 存放所有游戏数据 (JSON文件) 的目录路径。
        """
        self._data_path = data_path 
        
        self._move_db: Dict[str, MoveDataModel] = {}
        self._pokemon_db: Dict[str, PokemonDataModel] = {}
        self._follow_up_sequences: Dict[str, List[List[Dict[str, Any]]]] = {}
        
        # 新增：用于存储从多个文件加载并合并的效果属性
        self._effects_db: Dict[str, Any] = {}
        # 新增：用于存储属性克制表
        self._type_chart: Dict[str, Any] = {}
        
        # 启动数据加载流程
        self._load_data(self._data_path)

    def _load_data(self, data_path: Path):
        """
        【核心重构】从多个JSON文件中加载所有游戏数据，并将不同类别的效果合并。
        """
        try:
            # 1. 加载技能数据
            with open(data_path / "moves.json", 'r', encoding='utf-8') as f:
                raw_moves = json.load(f)
                for name, data in raw_moves.items():
                    try:
                        move_model = MoveDataModel.model_validate(data)
                        self._move_db[name] = move_model
                        if move_model.on_follow_up:
                            for seq_id, steps_raw in move_model.on_follow_up.items():
                                self._follow_up_sequences[seq_id] = [[eff.model_dump() for eff in step] for step in steps_raw]
                    except ValidationError as e:
                        logger.error(f"校验技能 '{name}' 数据时失败:\n{e}")

            # 2. 加载宝可梦数据
            with open(data_path / "pokemon.json", 'r', encoding='utf-8') as f:
                raw_pokemon = json.load(f)
                for name, data in raw_pokemon.items():
                    try:
                        self._pokemon_db[name] = PokemonDataModel.model_validate(data)
                    except ValidationError as e:
                        logger.error(f"校验宝可梦 '{name}' 数据时失败:\n{e}")
            
            # 3. 加载并合并所有效果数据
            with open(data_path / "status_conditions.json", 'r', encoding='utf-8') as f:
                self._effects_db.update(json.load(f))
            with open(data_path / "temporary_effects.json", 'r', encoding='utf-8') as f:
                self._effects_db.update(json.load(f))

            # 4. 加载属性克制表
            with open(data_path / "type_chart.json", 'r', encoding='utf-8') as f:
                self._type_chart = json.load(f)

        except FileNotFoundError as e:
            logger.error(f"核心游戏数据文件未找到: {e}", exc_info=True); raise
        except Exception as e:
            logger.error(f"从 {data_path} 加载游戏数据时发生未知严重错误: {e}", exc_info=True); raise
        
        # 更新校验逻辑，确保所有数据都已加载
        if not (self._move_db and self._pokemon_db and self._effects_db and self._type_chart):
            logger.error("数据工厂加载失败，部分或全部核心数据未能通过校验或加载。"); raise RuntimeError("宝可梦插件因数据校验失败而无法启动。")
        
        # 更新成功日志
        logger.info(f"宝可梦数据工厂加载成功: {len(self._move_db)}技能, {len(self._pokemon_db)}宝可梦, {len(self._effects_db)}效果, {len(self._type_chart)}属性克制")

    def get_all_pokemon_names(self) -> List[str]:
        """获取所有已加载的宝可梦名称列表。"""
        return list(self._pokemon_db.keys())

    def get_pokemon_data(self, name: str) -> Optional[PokemonDataModel]:
        """根据名称获取宝可梦的Pydantic数据模型。"""
        return self._pokemon_db.get(name)

    def get_move_template(self, name: str) -> Optional[Move]:
        """根据名称获取技能的模板实例。"""
        move_model = self._move_db.get(name)
        if not move_model: return None
        return Move(name=name, display=move_model.display.model_dump(), on_use=move_model.on_use.model_dump())
    
    # +++ 新增的公共访问方法 +++
    def get_effect_properties(self) -> Dict[str, Any]:
        """获取所有效果的属性定义（已从多个文件合并）。"""
        return self._effects_db

    def get_type_chart(self) -> Dict[str, Any]:
        """获取属性克制表。"""
        return self._type_chart

    def create_pokemon(self, name: str, level: int, move_names: Optional[List[str]] = None) -> Optional[Pokemon]:
        """
        创建一只宝可梦的战斗实例。

        Args:
            name: 宝可梦的名称。
            level: 宝可梦的等级。
            move_names: 要赋予的技能列表，如果为None则使用默认技能。

        Returns:
            一个 Pokemon 对象实例，或在找不到数据时返回 None。
        """
        pokemon_data_model = self.get_pokemon_data(name)
        if not pokemon_data_model:
            return None
            
        if move_names is None:
            move_names = pokemon_data_model.default_moves
            
        base_stats_data = pokemon_data_model.base_stats.model_dump()
        
        # 关键一步：将工厂自身 (self) 和天生免疫 (innate_immunities) 注入到 Pokemon 实例中。
        return Pokemon(
            name=name,
            level=level,
            types=pokemon_data_model.types,
            stats=base_stats_data,
            move_names=move_names,
            factory=self,
            innate_immunities=pokemon_data_model.innate_immunities
        )

    def get_follow_up_sequence(self, sequence_id: str) -> Optional[List[List[Dict[str, Any]]]]:
        """获取一个追击序列的具体效果步骤。"""
        return self._follow_up_sequences.get(sequence_id)