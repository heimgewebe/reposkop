from reposkop.canonical import sha256_json
from reposkop.observation import observe_checkout
from reposkop.report import build_report
from reposkop.schema_validation import validate_artifact


def test_observation_schema(git_repo):
    assert validate_artifact(observe_checkout(git_repo))["valid"] is True


def test_report_schema(git_repo):
    assert validate_artifact(build_report(git_repo))["valid"] is True


def test_tampered_observation_digest_is_rejected(git_repo):
    value = observe_checkout(git_repo)
    value["target"]["purpose"] = "tampered"
    result = validate_artifact(value)
    assert result["valid"] is False
    assert any(error.get("path") == "observation_sha256" for error in result["errors"])


def test_report_rejects_projection_bound_to_other_observation(git_repo):
    value = build_report(git_repo)
    value["projection"]["observation_sha256"] = "0" * 64
    value["report_sha256"] = sha256_json(
        {key: item for key, item in value.items() if key != "report_sha256"}
    )
    result = validate_artifact(value)
    assert result["valid"] is False
    assert any(error.get("path") == "projection" or error.get("path") == "projection/observation_sha256" for error in result["errors"])
