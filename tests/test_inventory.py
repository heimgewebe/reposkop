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
