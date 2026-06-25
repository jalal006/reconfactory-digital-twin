"""Recovery-action summaries for failed equipment."""

from __future__ import annotations

from uuid import uuid4

from .models import RecoveryAction


class ReconfigurationManager:
    def create_action(self, fault_id: str, machine_id: str) -> RecoveryAction:
        return RecoveryAction(
            action_id=f"R-{uuid4().hex[:10].upper()}",
            fault_id=fault_id,
            machine_id=machine_id,
            action_type="reroute_or_pause",
            explanation="Failed equipment was removed from scheduling. Compatible work is rerouted; incompatible work is paused safely.",
        )
