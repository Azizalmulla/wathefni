n:
                pass
            # Wave 1 — requisitions schema (dark; runtime gated by flags).
            try:
                import requisitions as _requisitions

                _requisitions.ensure_requisitions_schema(cur)
            except Exception:
                pass
        conn.commit()


def company_root(company_code: str | None) -> Path:
    return WORKSPACE / "data" / "companie
