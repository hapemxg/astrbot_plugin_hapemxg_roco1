# battle_logic/effects/__init__.py

from .base_effect import BaseEffect
from .deal_damage import DealDamageEffect
from .stat_change import StatChangeEffect
from .apply_status import ApplyStatusEffect
from .restore_health import RestoreHealthEffect
from .start_sequence import StartSequenceEffect

EFFECT_HANDLER_MAP = {
    "deal_damage": DealDamageEffect,
    "stat_change": StatChangeEffect,
    "apply_status": ApplyStatusEffect,
    "restore_health": RestoreHealthEffect,
    "start_sequence": StartSequenceEffect,
}