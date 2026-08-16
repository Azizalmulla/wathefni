# R5H historical proof

- Launch freezes `survey_version_id` + audience. Creating version 2 with new wording does not rewrite the launched pin.
- C5 writes immutable `eng_audit_events` for create survey / version / campaign, launch, action plan, close, enable/disable.
- `list_history` returns campaign-scoped audit (entity_id or `detail.campaign_id`) and can reconstruct launch/create from the canonical campaign row if audit is sparse.
- Disable preserves campaigns and sets `history_preserved=true`. Disabled workspace does not expose history through a generic HR fallback (`history=None`, `unavailable`).
