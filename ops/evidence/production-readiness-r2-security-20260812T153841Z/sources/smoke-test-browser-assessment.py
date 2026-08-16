from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    html = app.public_assessment_html()
    assert_true("state.attempt.progress_version" in html, "answer POST must bind progress_version to render(state)")
    assert_true("data.attempt.progress_version" not in html, "undefined data.attempt.progress_version must not remain")
    assert_true("replaceChildren" in html, "item transitions must use atomic DOM replace for Safari")
    assert_true("Saving your answer" in html, "pending save chrome must keep content non-empty between items")
    assert_true("transform:translateY(-1px)" not in html, "choice hover transform can cause Safari paint flashes")
    assert_true("100svh" in html, "viewport height should use svh for Mobile Safari chrome")
    assert_true("cache: 'no-store'" in html or 'cache: "no-store"' in html, "assessment fetches must disable store cache")

    attempt_id = "11111111-1111-4111-8111-111111111111"
    attempt = {
        "attempt_id": attempt_id,
        "company_code": "WATHEFNI",
        "app_key": "96500000000-WATHEFNI-ACCOUNTING",
        "phone": "96500000000",
        "candidate_name": "Test Candidate",
        "position_title": "Accounting",
        "battery_key": app.ASSESSMENT_BATTERY_KEY,
        "status": "pending",
        "current_item_index": 0,
        "total_items": 2,
    }
    items = [
        {
            "item_id": "item_1",
            "item_order": 0,
            "section": "numerical_reasoning",
            "prompt_text": "Question one?",
            "choices": [{"key": "A", "text": "One"}, {"key": "B", "text": "Two"}, {"key": "C", "text": "Three"}, {"key": "D", "text": "Four"}],
            "answer_key": "A",
            "scoring": {"max_score": 1},
        },
        {
            "item_id": "item_2",
            "item_order": 1,
            "section": "verbal_reasoning",
            "prompt_text": "Question two?",
            "choices": [{"key": "A", "text": "One"}, {"key": "B", "text": "Two"}, {"key": "C", "text": "Three"}, {"key": "D", "text": "Four"}],
            "answer_key": "B",
            "scoring": {"max_score": 1},
        },
    ]
    completed: list[bool] = []

    originals = {
        "company_has_module": app.company_has_module,
        "assessment_attempt_by_id": app.assessment_attempt_by_id,
        "start_assessment_attempt": app.start_assessment_attempt,
        "assessment_next_item": app.assessment_next_item,
        "record_assessment_response": app.record_assessment_response,
        "complete_assessment_attempt": app.complete_assessment_attempt,
    }

    def fake_attempt_by_id(_attempt_id: str):
        return dict(attempt) if _attempt_id == attempt_id else None

    def fake_start(_attempt_id: str):
        attempt["status"] = "in_progress"
        return dict(attempt)

    def fake_next_item(current_attempt):
        idx = int(current_attempt.get("current_item_index") or 0)
        return items[idx] if idx < len(items) and current_attempt.get("status") != "completed" else None

    def fake_record(current_attempt, item, response_text, selected_key):
        attempt["current_item_index"] = int(attempt["current_item_index"]) + 1
        return {"response": {"item_id": item["item_id"], "selected_key": selected_key}, "attempt": dict(attempt)}

    def fake_complete(current_attempt):
        attempt["status"] = "completed"
        completed.append(True)
        return {"attempt": dict(attempt), "score": {"percent": 100}, "report_json": {}}

    try:
        app.company_has_module = lambda company, module: True
        app.assessment_attempt_by_id = fake_attempt_by_id
        app.start_assessment_attempt = fake_start
        app.assessment_next_item = fake_next_item
        app.record_assessment_response = fake_record
        app.complete_assessment_attempt = fake_complete

        # R2: link signing needs a dedicated secret; there is no fallback key.
        os.environ["WATHEFNI_ASSESSMENT_LINK_SECRET"] = "smoke-assessment-link-secret-2f7c9d4b1a6e"
        token = app.sign_assessment_token(attempt_id, int(app.time_module.time()) + 60)
        assert_true(app.verify_assessment_token(attempt_id, token), "signed assessment token should verify")
        assert_true(not app.verify_assessment_token("wrong-attempt", token), "token must be bound to attempt id")
        assert_true(
            not app.verify_assessment_token(attempt_id, token + "x"),
            "tampered assessment token must not verify",
        )

        client = TestClient(app.app)
        state = client.post(f"/assessment/{attempt_id}/state?token={token}").json()
        assert_true(state["attempt"]["status"] == "in_progress", "opening browser assessment should start attempt")
        assert_true(state["item"]["item_id"] == "item_1", "state should expose first unanswered item")
        assert_true("answer_key" not in state["item"], "public item must not leak answer key")

        next_state = client.post(f"/assessment/{attempt_id}/answer?token={token}", json={"selected_key": "A"}).json()
        assert_true(next_state["item"]["item_id"] == "item_2", "answer should advance to next question")

        done_state = client.post(f"/assessment/{attempt_id}/answer?token={token}", json={"selected_key": "B"}).json()
        assert_true(done_state["completed"] is True, "final answer should complete assessment")
        assert_true(bool(completed), "completion should call existing complete_assessment_attempt path")
    finally:
        for name, value in originals.items():
            setattr(app, name, value)

    print("browser assessment smoke tests passed")


if __name__ == "__main__":
    main()
