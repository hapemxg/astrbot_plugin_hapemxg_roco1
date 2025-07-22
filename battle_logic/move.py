# battle_logic/move.py

from typing import Dict, Optional, List, Any

class Move:
    def __init__(self, name: str, display: Dict[str, Any], on_use: Dict[str, Any], **kwargs):
        self.name = name
        
        # 从 'display' 字典中读取面板显示属性
        self.display_power = display.get("power", 0)
        self.type = display.get("type", "一般")
        self.category = display.get("category", "status")
        self.description = display.get("description", "没有描述。")

        # 【核心修复】将PP设为可选属性，以优雅地处理“挣扎”
        # 如果JSON中没有定义pp，则max_pp为None
        self.max_pp: Optional[int] = display.get("pp")
        self.current_pp: Optional[int] = self.max_pp

        # 从 'on_use' 字典中读取实际战斗属性
        self.priority = on_use.get("priority", 0) # 挣扎的priority应为0
        self.accuracy = on_use.get("accuracy", 100)
        self.guaranteed_hit = on_use.get("guaranteed_hit", False)
        self.effects = on_use.get("effects", [])