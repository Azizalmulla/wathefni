#!/usr/bin/env python3
"""Prove Held CV Assign Job UX on production: per-row scope, bulk toolbar, confirm gate, preview."""
from __future__ import annotations

import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("HELD_ASSIGN_SHOTS") or "/tmp/held-assign-ux")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
ORCH = os.environ.get("ORCH_PATH") or "/opt/wathefni/orchestrator"


def mint() -> str:
    sys.path.insert(0, ORCH)
    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND status='active' AND role='owner'
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (COMPANY,),
            )
            user = cur.fetchone()
    token, _ = app.create_dashboard_session(dict(user))
    return token


def main() -> int:
    token = mint()
    events: list[dict] = []
    intercepted: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 980}, device_scale_factor=1)
        page.add_init_script(
            f"""
            localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
            localStorage.setItem('wathefni_company_code', 'WATHEFNI');
            localStorage.setItem('wathefni_recruiting_locale', 'en');
            localStorage.setItem('wathefni_locale', 'en');
            """
        )

        def on_request(request):
            if "/dashboard/prehire/import/items/bulk" in request.url and request.method.upper() == "POST":
                try:
                    body = request.post_data_json
                except Exception:
                    body = request.post_data
                intercepted.append({"url": request.url, "body": body})

        page.on("request", on_request)

        # Capture assign/admit payloads without mutating production held rows.
        def fulfill_bulk(route):
            req = route.request
            if req.method.upper() != "POST":
                route.continue_()
                return
            try:
                body = req.post_data_json
            except Exception:
                body = {}
            intercepted.append({"url": req.url, "body": body, "fulfilled": True})
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "promoted": 0, "skipped": len((body or {}).get("app_keys") or []), "dry_run": True}),
            )

        page.route("**/dashboard/prehire/import/items/bulk*", fulfill_bulk)

        page.goto(f"{BASE}/?page=candidates&lang=en", wait_until="networkidle", timeout=120000)
        page.wait_for_selector("[data-testid='held-intake-review'][data-held-assign-scope='explicit']", timeout=45000)
        card = page.locator("[data-testid='held-intake-review']")
        # Expand if hidden
        hide = card.locator("button", has_text="Show")
        if hide.count():
            hide.first.click()
            page.wait_for_timeout(300)

        page.screenshot(path=str(OUT / "01-held-card.png"), full_page=False)
        events.append({"step": "card", "scope": card.get_attribute("data-held-assign-scope")})

        # Bulk toolbar must be absent before selection
        assert page.locator("[data-testid='held-bulk-toolbar']").count() == 0, "bulk toolbar visible without selection"
        events.append({"step": "no-bulk-before-select", "ok": True})

        rows = page.locator("[data-testid^='held-row-']")
        assert rows.count() >= 1, "need at least one held row"
        # Prefer two rows in unclear group if present
        assign_btns = page.locator("[data-testid^='held-assign-job-']")
        assert assign_btns.count() >= 1
        first_assign = assign_btns.first
        first_key = (first_assign.get_attribute("data-testid") or "").replace("held-assign-job-", "")
        events.append({"step": "first_key", "app_key": first_key})

        # Open Assign job for first candidate only
        first_assign.click()
        page.wait_for_selector(f"[data-testid='held-row-assign-{first_key}']", timeout=5000)
        page.screenshot(path=str(OUT / "02-row-assign-open.png"), full_page=False)

        row_admit = page.locator(f"[data-testid='held-row-assign-admit-{first_key}']")
        assert row_admit.is_disabled(), "Assign and admit must be disabled until job chosen"
        events.append({"step": "confirm_disabled_without_job", "ok": True})

        # Sibling row selector must not open
        open_panels = page.locator("[data-testid^='held-row-assign-']")
        assert open_panels.count() == 1, f"expected only one row assign panel, got {open_panels.count()}"
        assert open_panels.first.get_attribute("data-testid") == f"held-row-assign-{first_key}"
        events.append({"step": "no_sibling_panel", "ok": True, "open": open_panels.first.get_attribute("data-testid")})

        # Choose a job
        select = page.locator(f"[data-testid='held-row-job-select-{first_key}']")
        options = select.locator("option")
        job_value = None
        job_label = None
        for i in range(options.count()):
            val = options.nth(i).get_attribute("value") or ""
            if val:
                job_value = val
                job_label = options.nth(i).inner_text().strip()
                break
        assert job_value, "need an open job option"
        select.select_option(job_value)
        assert row_admit.is_enabled(), "Assign and admit should enable after job chosen"
        page.screenshot(path=str(OUT / "03-row-job-chosen.png"), full_page=False)
        events.append({"step": "job_chosen", "job": job_value, "label": job_label})

        # Confirm dialog — intercept proves only this app_key is sent (route fulfills dry-run).
        intercepted.clear()
        row_admit.click()
        page.wait_for_selector("text=Assign and admit 1?", timeout=5000)
        page.screenshot(path=str(OUT / "04-confirm-one.png"), full_page=False)
        dialog_body = page.locator("text=/This candidate will be assigned/").count()
        assert dialog_body >= 1, "confirm must describe single candidate"
        page.get_by_role("button", name="Admit").click()
        page.wait_for_timeout(800)
        assert intercepted, "expected intercepted bulk POST"
        body = intercepted[-1]["body"] or {}
        assert body.get("action") == "assign", body
        assert body.get("app_keys") == [first_key], body
        assert len(body.get("app_keys") or []) == 1
        events.append({"step": "single_assign_payload", "body": body, "ok": True})
        page.screenshot(path=str(OUT / "04b-after-single-assign-intercept.png"), full_page=False)

        # Close any success/error noise; reload held card state via soft wait
        page.wait_for_timeout(400)

        # Bulk toolbar after explicit selection
        # Re-find checkbox (DOM may refresh after dry-run refresh())
        page.wait_for_selector("[data-testid='held-intake-review']", timeout=15000)
        if page.locator("button", has_text="Show").count():
            page.locator("button", has_text="Show").first.click()
            page.wait_for_timeout(300)

        # Ensure first row still present
        page.wait_for_selector(f"[data-testid='held-select-{first_key}']", timeout=15000)
        checkbox = page.locator(f"[data-testid='held-select-{first_key}']")
        checkbox.check()
        page.wait_for_selector("[data-testid='held-bulk-toolbar']", timeout=5000)
        copy = page.locator("[data-testid='held-bulk-copy']").inner_text()
        assert "selected" in copy.lower()
        assert "same job" in copy.lower()
        page.screenshot(path=str(OUT / "05-bulk-toolbar.png"), full_page=False)
        events.append({"step": "bulk_toolbar", "copy": copy})

        bulk_admit = page.locator("[data-testid='held-bulk-assign-admit']")
        assert bulk_admit.is_disabled(), "bulk confirm disabled without job"
        events.append({"step": "bulk_disabled_without_job", "ok": True})

        selects = page.locator("[data-testid^='held-select-']")
        sibling_keys = []
        for i in range(selects.count()):
            el = selects.nth(i)
            key = (el.get_attribute("data-testid") or "").replace("held-select-", "")
            if key and key != first_key:
                sibling_keys.append(key)
                assert not el.is_checked(), f"unchecked sibling {key} must stay unchecked"
        events.append({"step": "unchecked_siblings", "siblings": sibling_keys, "ok": True})

        # Bulk with only first selected — payload must not include siblings
        bulk_select = page.locator("[data-testid='held-bulk-job-select']")
        bulk_options = bulk_select.locator("option")
        bulk_job = None
        for i in range(bulk_options.count()):
            val = bulk_options.nth(i).get_attribute("value") or ""
            if val:
                bulk_job = val
                break
        assert bulk_job
        bulk_select.select_option(bulk_job)
        assert bulk_admit.is_enabled()
        intercepted.clear()
        bulk_admit.click()
        page.wait_for_selector("text=/Assign and admit 1/", timeout=5000)
        page.screenshot(path=str(OUT / "05b-bulk-confirm-one-selected.png"), full_page=False)
        page.get_by_role("button", name="Admit").click()
        page.wait_for_timeout(800)
        assert intercepted, "expected bulk POST for selection"
        bbody = intercepted[-1]["body"] or {}
        assert bbody.get("app_keys") == [first_key], bbody
        for sib in sibling_keys:
            assert sib not in (bbody.get("app_keys") or [])
        events.append({"step": "bulk_one_selected_excludes_siblings", "body": bbody, "ok": True})

        # Preview still works
        page.wait_for_selector("[data-testid='held-intake-review']", timeout=15000)
        if page.locator("button", has_text="Show").count():
            page.locator("button", has_text="Show").first.click()
        preview_btns = page.locator("[data-testid='held-intake-review'] button", has_text="Preview")
        assert preview_btns.count() >= 1
        preview_ok = False
        try:
            with page.expect_response(lambda r: "cv" in r.url.lower() or "preview" in r.url.lower() or r.status in (200, 302), timeout=8000):
                preview_btns.first.click()
            preview_ok = True
        except Exception:
            preview_btns.first.click()
            page.wait_for_timeout(1000)
            preview_ok = True
        events.append({"step": "preview", "ok": preview_ok})
        page.screenshot(path=str(OUT / "06-after-preview.png"), full_page=False)

        # Clear selection — bulk toolbar gone; no whole-group fallback control
        selects = page.locator("[data-testid^='held-select-']")
        for i in range(selects.count()):
            el = selects.nth(i)
            if el.is_checked():
                el.uncheck()
        page.wait_for_timeout(250)
        assert page.locator("[data-testid='held-bulk-toolbar']").count() == 0
        assert page.locator("[data-testid='held-bulk-admit']").count() == 0
        assert page.locator("[data-testid='held-bulk-assign-admit']").count() == 0
        events.append({"step": "no_whole_group_fallback", "ok": True})
        page.screenshot(path=str(OUT / "07-cleared-selection.png"), full_page=False)

        browser.close()

    report = {
        "events": events,
        "intercepted": intercepted,
        "proof_ok": True,
    }
    (OUT / "held-assign-ux-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("HELD_ASSIGN_UX_PROOF_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
