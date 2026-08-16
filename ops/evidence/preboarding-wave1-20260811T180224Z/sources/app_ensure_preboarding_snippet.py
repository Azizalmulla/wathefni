ption:
                pass
            # Wave 1 — preboarding schema (dark; runtime gated by flags).
            try:
                import preboarding as _preboarding

                _preboarding.ensure_preboarding_schema(cur)
            except Exception:
                pass
        conn.commit()


def company_root(company_code: str | None) -> Path:
    return WORKSPACE / "data" / "companies
