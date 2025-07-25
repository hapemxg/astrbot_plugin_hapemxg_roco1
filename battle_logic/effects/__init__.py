# battle_logic/effects/__init__.py

from .base_effect import BaseEffect
from .deal_damage import DealDamageEffect
from .stat_change import StatChangeEffect
from .apply_status import ApplyStatusEffect
from .restore_health import RestoreHealthEffect
from .start_sequence import StartSequenceEffect
from .remove_status import RemoveStatusEffect
from .purge_all_status import PurgeAllStatusEffect
from .reset_negative_stats import ResetNegativeStatsEffect
from .toggle_immunity import ToggleImmunityEffect

EFFECT_HANDLER_MAP = {
    "deal_damage": DealDamageEffect,
    "stat_change": StatChangeEffect,
    "apply_status": ApplyStatusEffect,
    "restore_health": RestoreHealthEffect,
    "start_sequence": StartSequenceEffect,
    "remove_status": RemoveStatusEffect,
    "purge_all_status": PurgeAllStatusEffect,
    "reset_negative_stats": ResetNegativeStatsEffect,
    "toggle_immunity": ToggleImmunityEffect,
}