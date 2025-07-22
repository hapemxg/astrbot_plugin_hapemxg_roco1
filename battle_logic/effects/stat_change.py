# battle_logic/effects/stat_change.py
import random
from typing import List, TYPE_CHECKING
from .base_effect import BaseEffect
from ..constants import Stat

if TYPE_CHECKING:
    from ..pokemon import Pokemon
    from ..move import Move
    from ..battle import Battle

class StatChangeEffect(BaseEffect):
    """
    【已重构】效果处理器：改变目标的能力等级或暴击等级。
    此版本遵循封装原则，调用Pokemon对象的专用方法来执行状态变化。
    """
    def execute(self, attacker: 'Pokemon', defender: 'Pokemon', move: 'Move', log: List[str]):
        """
        执行能力变化逻辑。
        """
        # 根据effect_data确定效果的目标
        target = attacker if self.effect_data.get("target") == "self" else defender
        
        # 遍历JSON中定义的所有能力变化
        for change_info in self.effect_data.get("changes", []):
            try:
                # 从字符串动态获取Stat枚举成员
                stat_to_change = Stat(change_info["stat"])
                change_amount = change_info["change"]

                success = False
                message = ""

                # 【核心】根据属性类型，调用Pokemon对象上对应的专用方法
                if stat_to_change == Stat.CRIT_RATE:
                    # 调用暴击等级变化接口
                    success, message = target.change_crit_stage(change_amount)
                else:
                    # 调用常规能力等级变化接口
                    success, message = target.apply_stat_change(stat_to_change, change_amount)

                # 如果方法返回了成功和消息，则记录到日志中
                if success and message:
                    log.append(f"  {message}")
                elif message: # 即使不成功，也可能有利好消息（如“无法再提升了”）
                    log.append(f"  {message}")

            except ValueError:
                # 如果JSON中的stat字符串无效，记录一个警告
                log.append(f"（系统警告：在moves.json中发现无效的stat名称 '{change_info.get('stat')}'）")
