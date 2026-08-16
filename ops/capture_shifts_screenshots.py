#!/usr/bin/env python3
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR = Path('/Users/azizalmulla/Desktop/claw/ops/evidence/shifts-ux-closure-screenshots')
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHROMIUM = '/opt/homebrew/bin/chromium'
BASE_URL = 'http://localhost:5199/dashboard'

DENSE_SHIFTS = [
    {
        "shift_id": "sh-1",
        "employee_key": "EMP-1",
        "employee_name": "Ali Mohammad",
        "shift_date": "2026-08-03",
        "start_time": "08:00",
        "end_time": "16:00",
        "status": "scheduled",
        "assignment_type": "operations",
        "role": "Ops Lead",
        "site_key": "Kuwait City",
        "team_key": "Operations",
    },
    {
        "shift_id": "sh-2",
        "employee_key": "EMP-1",
        "employee_name": "Ali Mohammad",
        "shift_date": "2026-08-05",
        "start_time": "08:00",
        "end_time": "16:00",
        "status": "scheduled",
        "assignment_type": "operations",
        "role": "Ops Lead",
        "site_key": "Kuwait City",
        "team_key": "Operations",
    },
    {
        "shift_id": "sh-3",
        "employee_key": "EMP-2",
        "employee_name": "Sara Ahmad",
        "shift_date": "2026-08-03",
        "start_time": "09:00",
        "end_time": "17:00",
        "status": "scheduled",
        "assignment_type": "guest",
        "role": "Front Desk",
        "site_key": "Hawalli",
        "team_key": "Guest Services",
    },
    {
        "shift_id": "sh-4",
        "employee_key": "EMP-2",
        "employee_name": "Sara Ahmad",
        "shift_date": "2026-08-04",
        "start_time": "09:00",
        "end_time": "17:00",
        "status": "scheduled",
        "assignment_type": "guest",
        "role": "Front Desk",
        "site_key": "Hawalli",
        "team_key": "Guest Services",
    },
    {
        "shift_id": "sh-5",
        "employee_key": "EMP-3",
        "employee_name": "Noura Al-Sabah",
        "shift_date": "2026-08-05",
        "start_time": "21:00",
        "end_time": "05:00",
        "status": "scheduled",
        "assignment_type": "night",
        "role": "Night Supervisor",
        "is_overnight": True,
        "ends_next_day": True,
        "site_key": "Marina Branch",
        "team_key": "Night Team",
    },
    {
        "shift_id": "sh-6",
        "employee_key": "EMP-4",
        "employee_name": "Fahad Al-Enezi",
        "shift_date": "2026-08-06",
        "start_time": "14:00",
        "end_time": "22:00",
        "status": "scheduled",
        "assignment_type": "event",
        "role": "Special Event Host",
        "site_key": "Salmiya",
        "team_key": "Events",
    },
    {
        "shift_id": "sh-7",
        "employee_key": "EMP-4",
        "employee_name": "Fahad Al-Enezi",
        "shift_date": "2026-08-07",
        "start_time": "10:00",
        "end_time": "18:00",
        "status": "conflicted",
        "ui_state": "conflicted",
        "assignment_type": "event",
        "role": "Special Event Host",
        "site_key": "Salmiya",
        "team_key": "Events",
    },
]

SPARSE_SHIFTS = DENSE_SHIFTS[:2]

def setup_context(context, shifts_data):
    context.add_init_script("""
        localStorage.setItem('wathefni_dashboard_token', 'mock-token');
        localStorage.setItem('wathefni_company_code', 'WATHEFNI');
        localStorage.setItem('wathefni_hr_phone', '96555511122');
    """)

    def handle_route(route, request):
        url = request.url
        if "/bootstrap" in url or "/summary" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "user": {"name": "Admin Operator", "role": "owner"},
                    "company": {"company_code": "WATHEFNI", "name": "Wathefni Kuwait"},
                    "available_modules": [{"key": "shifts", "label": "Shifts"}],
                    "enabled_modules": ["shifts"],
                    "access": {
                        "permissions": [
                            "shifts.manage",
                            "shifts.write",
                            "shifts.read",
                            "posthire:shifts:read",
                            "posthire:shifts:write",
                            "posthire:shifts:manage",
                        ]
                    },
                    "user_access": {
                        "permissions": [
                            "shifts.manage",
                            "shifts.write",
                            "shifts.read",
                            "posthire:shifts:read",
                            "posthire:shifts:write",
                            "posthire:shifts:manage",
                        ]
                    },
                    "permissions": [
                        "shifts.manage",
                        "shifts.write",
                        "shifts.read",
                        "posthire:shifts:read",
                        "posthire:shifts:write",
                        "posthire:shifts:manage",
                    ],
                }),
            )
        elif "/posthire/shifts" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "shifts": shifts_data,
                    "swaps": [],
                    "availability": [],
                    "reconciliation": [],
                    "reminders": [],
                    "templates": [],
                    "periods": [],
                    "open_shifts": [],
                    "coverage_rules": [],
                    "rotation_patterns": [],
                    "rotation_assignments": [],
                    "pam_exports": [],
                }),
            )
        elif "/setup/org-units" in url or "/org-units" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "org_units": [
                        {"org_unit_id": "u1", "unit_type": "team", "name": "Operations", "unit_key": "Operations"},
                        {"org_unit_id": "u2", "unit_type": "team", "name": "Guest Services", "unit_key": "Guest Services"},
                    ]
                }),
            )
        elif "/dashboard/prehire/" in url or "/dashboard/calendar/" in url or "/dashboard/setup/" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({}),
            )
        else:
            route.continue_()

    context.route("**", handle_route)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)

        # 1. Dense Week EN
        context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
        setup_context(context, DENSE_SHIFTS)
        page = context.new_page()
        page.goto(f"{BASE_URL}/?page=shifts&lang=en", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "01-dense-week-en.png"))
        print("Captured 01-dense-week-en.png")
        context.close()

        # 2. Sparse Week EN
        context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
        setup_context(context, SPARSE_SHIFTS)
        page = context.new_page()
        page.goto(f"{BASE_URL}/?page=shifts&lang=en", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "02-sparse-week-en.png"))
        print("Captured 02-sparse-week-en.png")
        context.close()

        # 3. Empty Week EN
        context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
        setup_context(context, [])
        page = context.new_page()
        page.goto(f"{BASE_URL}/?page=shifts&lang=en", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "03-empty-week-en.png"))
        print("Captured 03-empty-week-en.png")
        context.close()

        # 4. Drawer Open EN
        context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
        setup_context(context, DENSE_SHIFTS)
        page = context.new_page()
        page.goto(f"{BASE_URL}/?page=shifts&lang=en", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.click('[data-primary-action="schedule"]')
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT_DIR / "04-drawer-open-en.png"))
        print("Captured 04-drawer-open-en.png")
        context.close()

        # 5. Mobile View EN
        context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        setup_context(context, DENSE_SHIFTS)
        page = context.new_page()
        page.goto(f"{BASE_URL}/?page=shifts&lang=en", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "05-mobile-view-en.png"))
        print("Captured 05-mobile-view-en.png")
        context.close()

        # 6. Dense Week AR (RTL)
        context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
        setup_context(context, DENSE_SHIFTS)
        page = context.new_page()
        page.goto(f"{BASE_URL}/?page=shifts&lang=ar", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "06-dense-week-ar.png"))
        print("Captured 06-dense-week-ar.png")
        context.close()

        browser.close()

if __name__ == "__main__":
    run()
