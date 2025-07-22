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
    def __init__(self, data_path: Path):
        # 【核心修复】将 data_path 保存为实例属性
        self._data_path = data_path 
        
        self._move_db: Dict[str, MoveDataModel] = {}
        self._pokemon_db: Dict[str, PokemonDataModel] = {}
        self._follow_up_sequences: Dict[str, List[List[Dict[str, Any]]]] = {}
        
        # 现在使用实例属性来加载数据，确保一致性
        self._load_data(self._data_path)

    def _load_data(self, data_path: Path):
        try:
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
            with open(data_path / "pokemon.json", 'r', encoding='utf-8') as f:
                raw_pokemon = json.load(f)
                for name, data in raw_pokemon.items():
                    try:
                        self._pokemon_db[name] = PokemonDataModel.model_validate(data)
                    except ValidationError as e:
                        logger.error(f"校验宝可梦 '{name}' 数据时失败:\n{e}")
        except FileNotFoundError as e:
            logger.error(f"游戏数据文件未找到: {e}", exc_info=True); raise
        except Exception as e:
            logger.error(f"从 {data_path} 加载游戏数据时发生未知严重错误: {e}", exc_info=True); raise
        if not (self._move_db and self._pokemon_db):
            logger.error("数据工厂加载失败，部分或全部数据未能通过校验。"); raise RuntimeError("宝可梦插件因数据校验失败而无法启动。")
        logger.info(f"宝可梦数据工厂校验并加载成功: {len(self._move_db)}技能, {len(self._pokemon_db)}宝可梦")

    def get_all_pokemon_names(self) -> List[str]: return list(self._pokemon_db.keys())
    def get_pokemon_data(self, name: str) -> Optional[PokemonDataModel]: return self._pokemon_db.get(name)
    def get_move_template(self, name: str) -> Optional[Move]:
        move_model = self._move_db.get(name)
        if not move_model: return None
        return Move(name=name, display=move_model.display.model_dump(), on_use=move_model.on_use.model_dump())
    
    # 【新增辅助方法】根据技能名获取其启动的序列ID
    def get_sequence_id_for_move(self, move_name: str) -> Optional[str]:
        """如果一个技能能启动序列，返回其序列ID，否则返回None。"""
        move_model = self._move_db.get(move_name)
        if move_model and move_model.on_follow_up:
            # 假设一个技能只启动一个序列，返回第一个找到的ID
            return next(iter(move_model.on_follow_up))
        return None

    def create_pokemon(self, name: str, level: int, move_names: Optional[List[str]] = None) -> Optional[Pokemon]:
        pokemon_data_model = self.get_pokemon_data(name)
        if not pokemon_data_model: return None
        if move_names is None: move_names = pokemon_data_model.default_moves
        base_stats_data = pokemon_data_model.base_stats.model_dump()
        return Pokemon(name=name, level=level, types=pokemon_data_model.types, stats=base_stats_data, move_names=move_names, factory=self)

    def get_follow_up_sequence(self, sequence_id: str) -> Optional[List[List[Dict[str, Any]]]]:
        return self._follow_up_sequences.get(sequence_id)