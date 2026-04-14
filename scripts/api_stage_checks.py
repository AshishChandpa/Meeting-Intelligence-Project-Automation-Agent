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

    create = client.post("/api/projects", json={"name": "stage-check", "transcript": transcript}).json()
    project_id = create["project_id"]

    client.post(f"/api/projects/{project_id}/stage/parse/approve")

    ask = client.post(
        f"/api/projects/{project_id}/stage/clarify/ask",
        json={"question": "Can we fit reporting in Sprint 2?"},
    )
    print("ask_status:", ask.status_code)

    client.post(f"/api/projects/{project_id}/stage/clarify/done")
    client.post(
        f"/api/projects/{project_id}/stage/sow/feedback",
        json={"feedback": "Please include explicit out-of-scope and open items."},
    )
    approve_sow = client.post(f"/api/projects/{project_id}/stage/sow/approve")
    print("approve_sow_status:", approve_sow.status_code)

    state = client.get(f"/api/projects/{project_id}").json()
    task_id = (state.get("tasks") or [{}])[0].get("id")
    target_sprint = (state.get("sprints") or [{}])[-1].get("name")

    if task_id and target_sprint:
        move = client.post(
            f"/api/projects/{project_id}/stage/sprint/move-task",
            json={"task_id": task_id, "sprint_name": target_sprint},
        )
        print("move_status:", move.status_code)

        refreshed = client.get(f"/api/projects/{project_id}").json()
        print("warnings_after_move:", len(refreshed.get("sprint_warnings") or []))


if __name__ == "__main__":
    main()

