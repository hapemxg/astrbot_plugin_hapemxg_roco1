"""
Pydantic 数据模型，用于校验和解析从 JSON 加载的游戏数据。
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Move Models ---

class EffectModel(BaseModel):
    """校验单个效果的结构"""
    handler: str
    chance: int = 100
    
    # 【修复】使用 Pydantic V2 推荐的 model_config 字典
    # 来允许 'options' 等在模型中未明确定义的额外字段。
    model_config = {
        "extra": "allow"
    }

class DisplayModel(BaseModel):
    """校验技能的 'display' 部分"""
    power: int = 0
    pp: int
    type: str
    category: str
    description: str = "没有描述。"

class OnUseModel(BaseModel):
    """校验技能的 'on_use' 部分"""
    # 【核心修改】将 priority 的默认值从 0 修改为 8
    priority: int = 8 
    accuracy: Optional[int] = 100
    guaranteed_hit: bool = False
    effects: List[EffectModel] = Field(default_factory=list)

class MoveDataModel(BaseModel):
    """一个完整技能的数据模型"""
    display: DisplayModel
    on_use: OnUseModel
    on_follow_up: Optional[Dict[str, List[List[EffectModel]]]] = None

# --- Pokemon Models ---

class BaseStatsModel(BaseModel):
    """校验宝可梦的基础属性"""
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int
    crit_points: int = 0

class PokemonDataModel(BaseModel):
    """一个完整宝可梦的数据模型"""
    types: List[str]
    base_stats: BaseStatsModel
    default_moves: List[str]
    extra_moves: List[str] = Field(default_factory=list)
    # 【新增】添加一个可选的天生免疫列表
    innate_immunities: Optional[List[str]] = None