from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.main import app


def main() -> None:
    client = TestClient(app)
    transcript = (ROOT / "Software Co _ Smart Money Discovery  Transcript.txt").read_text(encoding="utf-8")

    health = client.get("/health")
    print("health:", health.status_code, health.json().get("status"))

    create = client.post("/api/projects", json={"name": "smoke-api", "transcript": transcript})
    print("create:", create.status_code)
    create_data = create.json()
    project_id = create_data["project_id"]

    stage1 = client.get(f"/api/projects/{project_id}").json()
    print("stage_after_create:", stage1.get("current_stage"))

    approve1 = client.post(f"/api/projects/{project_id}/stage/parse/approve")
    print("approve_stage1:", approve1.status_code)

    stage2 = client.get(f"/api/projects/{project_id}").json()
    print("stage_after_stage1:", stage2.get("current_stage"), "questions:", len(stage2.get("questions") or []))

    done2 = client.post(f"/api/projects/{project_id}/stage/clarify/done")
    print("done_stage2:", done2.status_code)

    stage3 = client.get(f"/api/projects/{project_id}").json()
    print("stage_after_stage2:", stage3.get("current_stage"), "sow_chars:", len(stage3.get("sow") or ""))


if __name__ == "__main__":
    main()

