from __future__ import annotations

import threading
import time

import reposkop.inventory as inventory_module
from reposkop.inventory import inspect_inventory


def test_inventory_is_explicit_and_bounded(git_repo):
    config = {
        "schema_version": 1,
        "kind": "reposkop_inventory_config",
        "targets": [{"path": str(git_repo), "purpose": "test"}],
    }
    result = inspect_inventory(config)
    assert result["target_count"] == 1
    assert result["discovery_performed"] is False
    assert result["observations"][0]["target"]["purpose"] == "test"


def test_inventory_preserves_target_order_when_parallel_observations_finish_out_of_order(
    monkeypatch,
):
    def fake_observe(path, *, explicit_role=None, purpose=None):
        del path, explicit_role
        time.sleep({"slow": 0.03, "fast": 0.001, "medium": 0.01}[purpose])
        return {"target": {"purpose": purpose}}

    monkeypatch.setattr(inventory_module, "observe_checkout", fake_observe)
    config = {
        "schema_version": 1,
        "kind": "reposkop_inventory_config",
        "targets": [
            {"path": "/tmp/reposkop-slow", "purpose": "slow"},
            {"path": "/tmp/reposkop-fast", "purpose": "fast"},
            {"path": "/tmp/reposkop-medium", "purpose": "medium"},
        ],
    }

    result = inspect_inventory(config)

    assert [item["target"]["purpose"] for item in result["observations"]] == [
        "slow",
        "fast",
        "medium",
    ]


def test_inventory_bounds_parallel_observation_workers(monkeypatch):
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_observe(path, *, explicit_role=None, purpose=None):
        del path, explicit_role
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.02)
            return {"target": {"purpose": purpose}}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(inventory_module, "observe_checkout", fake_observe)
    config = {
        "schema_version": 1,
        "kind": "reposkop_inventory_config",
        "targets": [
            {"path": f"/tmp/reposkop-target-{index}", "purpose": f"target-{index}"}
            for index in range(24)
        ],
    }

    result = inspect_inventory(config)

    assert result["target_count"] == 24
    assert 1 < max_active <= inventory_module._MAX_OBSERVATION_WORKERS
