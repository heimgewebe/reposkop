from pathlib import Path

from reposkop.roles import classify_role


def test_managed_repoground_path_wins():
    role, reasons = classify_role(
        path=Path("/home/alex/repos/.repoground-sources/heimgewebe__x__main"),
        git_dir=None,
        git_common_dir=None,
    )
    assert role == "managed_repoground_source"
    assert reasons == ["path:.repoground-sources"]


def test_explicit_role_is_validated():
    role, reasons = classify_role(
        path=Path("/tmp/x"),
        git_dir=None,
        git_common_dir=None,
        explicit_role="deployment_source",
    )
    assert role == "deployment_source"
    assert reasons == ["explicit_role"]
