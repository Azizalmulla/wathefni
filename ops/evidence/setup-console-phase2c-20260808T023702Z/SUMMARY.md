# Setup Console Phase 2C smoke

PASS=35 FAIL=0

Scale: `{"synthetic_matcher": [{"n": 100, "matcher_ms": 0.06, "gain": 33, "lose": 17, "unchanged": 50}, {"n": 1000, "matcher_ms": 0.66, "gain": 333, "lose": 167, "unchanged": 500}, {"n": 10000, "matcher_ms": 6.0, "gain": 3333, "lose": 1667, "unchanged": 5000}], "live": {"search_page_ms": 24.79, "search_page_rows": 50, "search_total_count": 98, "preview_everyone_ms": 43.9, "preview_active_employees": 98}, "synthetic_from_api": [{"n": 100, "matcher_ms": 0.11, "gain": 33, "lose": 17, "unchanged": 50, "loads_full_roster_client_side": false}, {"n": 1000, "matcher_ms": 5.06, "gain": 333, "lose": 167, "unchanged": 500, "loads_full_roster_client_side": false}, {"n": 10000, "matcher_ms": 10.41, "gain": 3333, "lose": 1667, "unchanged": 5000, "loads_full_roster_client_side": false}]}`

Evidence: `/opt/wathefni/ops/evidence/setup-console-phase2c-20260808T023702Z`
