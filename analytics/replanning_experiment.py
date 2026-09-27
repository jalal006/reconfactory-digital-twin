"""Paired logical transport experiment, not a physics or navigation benchmark."""

from reconfactory import FactorySupervisor
from reconfactory.models import FaultType


def run_replanning_comparison() -> dict:
    results = {}
    for enabled in (False, True):
        factory = FactorySupervisor(
            enable_database=False,
            transport_mode="amr",
            vision_source="synthetic",
            maintenance_mode="rules",
            health_scheduling=False,
        )
        product = factory.create_product("red_block")
        factory.start()
        fault_tick = cancelled_tick = replanned_tick = recovered_tick = completed_tick = None
        old_id = None
        for tick in range(80):
            factory.transport.heartbeat(True)
            factory.tick()
            task = factory.transport.active
            if task:
                if task.supersedes_task_id:
                    replanned_tick = replanned_tick if replanned_tick is not None else tick
                if (
                    fault_tick is None
                    and task.destination == "station_a"
                    and task.phase == "delivery"
                ):
                    fault_tick, old_id = tick, task.task_id
                    factory.inject_fault("station_a", FaultType.OVERHEAT)
                    if not enabled:
                        # Reproduce the previous static policy: cancel, then require reset.
                        task.replan_state = None
                elif task.cancel_requested and task.status not in {"cancelled", "failed"}:
                    factory.transport.receive({**task.to_dict(), "status": "cancelled"})
                    cancelled_tick = tick
                elif task.status == "requested":
                    factory.transport.receive({**task.to_dict(), "status": "accepted"})
                elif task.status == "accepted":
                    factory.transport.receive({**task.to_dict(), "status": "navigating"})
                elif task.status == "navigating":
                    factory.transport.receive(
                        {
                            **task.to_dict(),
                            **(
                                {"phase": "delivery"}
                                if task.phase == "pickup"
                                else {"status": "delivered"}
                            ),
                        }
                    )
                    if (
                        old_id
                        and task.supersedes_task_id == old_id
                        and task.status == "delivered"
                    ):
                        recovered_tick = tick
            if product.status.value == "completed":
                completed_tick = tick
                break
        results["replanning" if enabled else "static"] = {
            "fault_tick": fault_tick,
            "completed_products": int(completed_tick is not None),
            "stranded_products": int(completed_tick is None),
            "successful_replans": int(recovered_tick is not None),
            "failed_replans": sum(
                e.event_type == "transport_replan_failed" for e in factory.events
            ),
            "cancel_latency_ticks": cancelled_tick - fault_tick,
            "replan_latency_ticks": None
            if replanned_tick is None
            else replanned_tick - cancelled_tick,
            "recovery_ticks": None if recovered_tick is None else recovered_tick - fault_tick,
            "completion_tick": completed_tick,
            "extra_navigation_distance_m": None,
            "production_completion_delay_ticks": None,
        }
    return {
        "scenario": "One red block, A overheat on first loaded delivery tick, no repair",
        "limitations": "Deterministic scripted action acknowledgements, not Nav2 physics. Units are logical ticks. Static never completes, so completion delay is undefined. Distance is not measured.",
        **results,
    }
