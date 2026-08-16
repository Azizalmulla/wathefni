import os
import sys

pid = sys.argv[1]
with open(f"/proc/{pid}/environ", "rb") as f:
    for item in f.read().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        try:
            os.environ[k.decode()] = v.decode()
        except Exception:
            pass

import app
import employee_status_approval as sa

company = "WATHEFNI"
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM dashboard_users WHERE company_code=%s ORDER BY updated_at DESC NULLS LAST LIMIT 40",
            (company,),
        )
        users = [dict(r) for r in cur.fetchall()]
        managers = []
        for u in users:
            normal = app._normal_dashboard_operator(u)
            perms = app.dashboard_effective_permissions_for_user(u, cur=cur)
            print(
                "user",
                str(u["user_id"]),
                u.get("email"),
                "normal",
                normal,
                "manage",
                "employees.manage" in perms,
                "approve",
                "employees.status.approve" in perms,
            )
            if normal and "employees.manage" in perms:
                managers.append(u)
        print("managers", len(managers))
        req = str(managers[0]["user_id"]) if managers else None
        print("requester", req)
        sa.ensure_employee_status_approval_schema(cur)
        el = sa.list_eligible_status_approvers(app, cur, company_code=company, exclude_user_id=req)
        print("eligible", el)
        el_all = sa.list_eligible_status_approvers(app, cur, company_code=company, exclude_user_id=None)
        print("eligible_all", el_all)
    conn.commit()
