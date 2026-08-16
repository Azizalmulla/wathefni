@app.get("/dashboard/prehire/assessments/queue")
def dashboard_prehire_assessments_queue_removed(
    context: dict[str, Any] = Depends(assessments_dashboard_context),
):
    """Tombstone for a never-shipped path.

    Historical probes sometimes hit ``/assessments/queue``. That path was never
    a product API — the live Assessments send cohort uses
    ``GET /dashboard/prehire/applications`` with ``overview_cohort`` /
    ``assessment_cohort``. Without this static route, ``queue`` was captured by
    ``/assessments/{attempt_id}`` and could surface as an opaque 500.
    """
    del context  # auth/entitlement still enforced via Depends
    raise HTTPException(
        status_code=410,
        detail={
            "error": "assessment_queue_route_removed",
            "message": (
                "This assessments queue path is not part of the product API. "
                "Use GET /dashboard/prehire/applications with overview_cohort "
                "and assessment_cohort (for example assessment_ready_to_send)."
            ),
        },
    )


