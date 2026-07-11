import json
from pathlib import Path
from src.fridgechef.security import validate_service_account_json


def test_service_account_validation(tmp_path: Path):
    p = tmp_path / "credentials.json"
    p.write_text(json.dumps({"type":"service_account","project_id":"p","client_email":"a@b","private_key":"x"}), encoding="utf-8")
    data = validate_service_account_json(p)
    assert data["project_id"] == "p"
