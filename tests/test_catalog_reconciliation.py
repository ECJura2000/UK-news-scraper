from pathlib import Path

import pytest

from scripts.audit_source_catalog import write_json
from scripts.reconcile_catalog_runtime import hashlib, json, reconcile

IDENTIFIER = "scotland:test"
ENDPOINT = "https://official.example/feed/"


def prepare(output: Path, *, python_success=False, python_code=0, rust_success=False, rust_code=0,
            evidence_endpoint=ENDPOINT):
    row_file = output / "sources" / f"{hashlib.sha256(IDENTIFIER.encode()).hexdigest()}.json"
    review = {"id": IDENTIFIER, "endpoint": ENDPOINT}
    write_json(row_file, {"id": IDENTIFIER, "outcome": "verified", "review": review})
    for runtime, success, code in (
        ("python", python_success, python_code), ("rust", rust_success, rust_code),
    ):
        write_json(output / "live-all" / f"failed-{runtime}-diagnostics.json", {
            "health": [{"source": IDENTIFIER, "success": success,
                        "endpoints": [{"url": evidence_endpoint, "status_code": code}]}],
        })
    return row_file, review


@pytest.mark.parametrize("code", [0, 403])
def test_default_reconciliation_requires_actual_failure_and_preserves_original_review(tmp_path, code):
    row_file, review = prepare(tmp_path, python_code=code, rust_code=code)
    reconcile(tmp_path, IDENTIFIER)
    reconcile(tmp_path, IDENTIFIER)
    result = json.loads(row_file.read_text())
    assert result["outcome"] == "network_or_access_error"
    assert result["previous_review"] == review
    assert "review" not in result
    assert result["failed_runtimes"] == ["python", "rust"]
    assert f"HTTP {code}" in result["reason"]
    assert set(result["runtime_verification"]) == {"python", "rust"}


@pytest.mark.parametrize("changes", [
    {"python_success": True, "python_code": 200},
    {"rust_success": True, "rust_code": 200},
    {"evidence_endpoint": "https://unrelated.example/feed/"},
    {"python_code": 200},
    {"rust_code": 200},
])
def test_success_or_unmatched_endpoint_cannot_create_a_hold(tmp_path, changes):
    row_file, _ = prepare(tmp_path, **changes)
    original = row_file.read_bytes()
    with pytest.raises(ValueError):
        reconcile(tmp_path, IDENTIFIER)
    assert row_file.read_bytes() == original


def test_single_rust_failure_records_python_backup_success_truthfully(tmp_path):
    row_file, _ = prepare(tmp_path, python_success=True, python_code=200, rust_code=403)
    reconcile(
        tmp_path, IDENTIFIER, runtimes=("rust",),
        python_evidence=tmp_path / "live-all/failed-python-diagnostics.json",
        rust_evidence=tmp_path / "live-all/failed-rust-diagnostics.json",
    )
    result = json.loads(row_file.read_text())
    assert result["failed_runtimes"] == ["rust"]
    assert "Rust HTTP 讀取失敗（HTTP 403）" in result["reason"]
    assert "Python 備援成功（HTTP 200）" in result["reason"]
    assert "Python 連線失敗" not in result["reason"]
    assert result["runtime_verification"]["python"]["health"]["success"] is True


def test_single_rust_without_python_evidence_does_not_claim_any_python_result(tmp_path):
    row_file, _ = prepare(tmp_path, python_success=True, python_code=200, rust_code=403)
    reconcile(tmp_path, IDENTIFIER, runtimes=("rust",))
    result = json.loads(row_file.read_text())
    assert "Python" not in result["reason"]
    assert set(result["runtime_verification"]) == {"rust"}
