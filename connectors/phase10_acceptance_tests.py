"""Phase 10 acceptance gate for MusabAI / NewAl-Cloud.

Focused release acceptance over the already-tested subsystems. The gate reuses
the exact tests that exercise Phase 10 behavior instead of duplicating their
implementation.
"""
from __future__ import annotations

import importlib
import sys
import unittest

SELECTED = [
    # Router: default text path, capability detection, vision safety, failover.
    ("newal_code.provider_pool_tests", "ProviderPoolTests",
     "test_free_pool_order_and_current_provider_is_not_repeated"),
    ("newal_code.provider_pool_tests", "ProviderPoolTests",
     "test_request_capabilities_detects_vision_tools_and_streaming"),
    ("newal_code.provider_pool_tests", "ProviderPoolTests",
     "test_vision_candidates_exclude_text_only_models"),
    ("newal_code.provider_pool_tests", "ProviderPoolTests",
     "test_switches_after_overload_and_reports_real_target"),

    # Termux: disconnected state, authenticated localhost bridge, restart/reconnect.
    ("newal_code.runtime_manager_tests", "RuntimeManagerTest",
     "test_disconnected_termux_is_unknown_not_false_missing_and_clears_cache"),
    ("newal_code.runtime_manager_tests", "RuntimeManagerTest",
     "test_mcp_stdio_lifecycle_uses_authenticated_process_request"),
    ("newal_code.termux_bridge_tests", "TermuxBridgeServerTest",
     "test_process_survives_bridge_restart_and_can_be_stopped"),

    # MCP: verified lifecycle start/stop/reconnect.
    ("newal_code.mcp_bundles_tests", "McpBundlesTest",
     "test_start_stop_and_reconnect_control_the_real_managed_process"),

    # Long-running tasks: real Stop, watchdog, hard timeout, resume/checkpoints.
    ("newal_code.task_supervisor_tests", "TaskSupervisorTests",
     "test_manual_stop_sets_real_cancel_and_preserves_resume_checkpoint"),
    ("newal_code.task_supervisor_tests", "TaskSupervisorTests",
     "test_watchdog_emits_heartbeat_then_cancels_stalled_operation"),
    ("newal_code.task_supervisor_tests", "TaskSupervisorTests",
     "test_hard_timeout_stops_after_repeated_stalls"),
    ("newal_code.task_state_tests", "TaskStateTests",
     "test_checkpoint_survives_reload_and_resumes_latest"),

    # Self-update: staging/verification barrier, rollback, hot-reload/native boundary.
    ("newal_code.evolution_tests", "EvolutionTests",
     "test_corrupted_staged_update_is_rejected_before_activation"),
    ("newal_code.evolution_tests", "EvolutionTests",
     "test_update_verification_failure_never_changes_active_pointer"),
    ("newal_code.evolution_tests", "EvolutionTests",
     "test_rollback_restores_last_verified_revision_not_arbitrary_path"),
    ("newal_code.evolution_tests", "EvolutionTests",
     "test_hot_reload_activation_never_overlays_python_or_native_files"),

    # Signing: APK identity remains pinned and verified by apksigner.
    ("connectors.test_signing_policy", "SigningPolicyTests",
     "test_apksigner_and_pinned_fingerprint_gate_are_mandatory"),
]


def build_suite() -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for module_name, class_name, method_name in SELECTED:
        module = importlib.import_module(module_name)
        case = getattr(module, class_name)
        suite.addTest(case(method_name))
    return suite


def main() -> int:
    suite = build_suite()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.testsRun != len(SELECTED):
        print(
            f"Phase 10 acceptance gate expected {len(SELECTED)} tests, "
            f"ran {result.testsRun}",
            file=sys.stderr,
        )
        return 2
    if not result.wasSuccessful():
        return 1
    print(f"PHASE10_ACCEPTANCE={result.testsRun}/{len(SELECTED)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
