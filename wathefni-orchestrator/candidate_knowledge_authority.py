"""Candidate Knowledge authority shell (Phase 1–3).

Phase 1: request-context, exact resolve, sibling aggregation, actionability.
Phase 2: canonical CV / facts / classification assembly after resolution.
Phase 3: application history, screening, assessments, interviews, ranking,
         notes federation, identity-state.

Does not register model tools, index, call Voyage, mutate storage, or run Phase 4+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from candidate_knowledge_errors import (
    ERROR_ACTOR_REQUIRED,
    ERROR_BACKEND_CURRENT_REQUIRED,
    ERROR_CANDIDATE_AMBIGUOUS,
    ERROR_CANDIDATE_NOT_FOUND,
    ERROR_CANDIDATE_RESTRICTED,
    ERROR_INVALID_CANDIDATE_REF,
    ERROR_MODULE_DISABLED,
    ERROR_NAME_ONLY_INVALID,
    ERROR_PERMISSION_DENIED,
    ERROR_PERMISSION_SUBJECT_MISMATCH,
    ERROR_SOURCE_READER_BLOCKED,
    ERROR_TENANT_SCOPE_REQUIRED,
    CandidateKnowledgeError,
)
from candidate_knowledge_phase3_readers import (
    read_applications,
    read_assessments,
    read_identity_state,
    read_interviews,
    read_notes,
    read_ranking_evaluations,
    read_screening_evidence,
)
from candidate_knowledge_readers import (
    read_canonical_cv,
    read_effective_classification,
    read_effective_facts,
)
from candidate_knowledge_store import (
    CandidateKnowledgeStore,
    InMemoryCandidateKnowledgeStore,
    PostgresCandidateKnowledgeStore,
)
from candidate_knowledge_types import (
    CANDIDATE_KNOWLEDGE_SCHEMA,
    CANDIDATE_REF_PREFIX,
    Actionability,
    CandidateKnowledgeRecord,
    CandidateKnowledgeSubject,
    CoverageItem,
    EvidenceRef,
    app_key_from_candidate_ref,
    candidate_ref_from_app_key,
)
from candidate_record_state_policy import (
    CandidateRecordStateDecision,
    evaluate_candidate_record_state,
)


PHASE1_VERSION = "candidate-knowledge-phase1-v1"
PHASE2_VERSION = "candidate-knowledge-phase2-v1"
PHASE3_VERSION = "candidate-knowledge-phase3-v1"
REQUIRED_PERMISSION = "prehire.read"
REQUIRED_MODULE = "pre_hiring"
REQUIRED_PERMISSION_AUTHORITY = "backend_current"

PHASE2_SECTIONS = frozenset({"canonical_cv", "effective_facts", "classifications"})
PHASE3_SECTIONS = frozenset(
    {
        "applications",
        "screening_evidence",
        "assessments",
        "interviews",
        "ranking_evaluations",
        "notes",
        "identity_state",
    }
)
FORBIDDEN_SOURCE_READER_NAMES = frozenset(
    {
        "semantic_documents",
        "candidates.profile",
        "applications.raw_json",
    }
)
PHASE4_PLUS_READER_NAMES = frozenset(
    {
        "chunk_index",
        "voyage_retrieval",
        "search_candidates",
    }
)
SOURCE_READER_NAMES = PHASE2_SECTIONS | PHASE3_SECTIONS | FORBIDDEN_SOURCE_READER_NAMES | PHASE4_PLUS_READER_NAMES

ModuleEnabledFn = Callable[[str, str], bool]


@dataclass(frozen=True)
class CandidateKnowledgeRequestContext:
    company_code: str
    actor_user_id: str
    permission_authority: str
    permission_subject_user_id: str
    permission_subject_company: str
    permissions: tuple[str, ...]
    modules_enabled: tuple[str, ...] = ()
    locale: str | None = None
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_code": self.company_code,
            "actor_user_id": self.actor_user_id,
            "permission_authority": self.permission_authority,
            "permission_subject_user_id": self.permission_subject_user_id,
            "permission_subject_company": self.permission_subject_company,
            "permissions": list(self.permissions),
            "modules_enabled": list(self.modules_enabled),
            "locale": self.locale,
            "request_id": self.request_id,
        }


@dataclass
class Phase1ResolvedSubject:
    candidate_ref: str
    company_code: str
    anchor_app_key: str
    candidate_key: str
    applications: list[dict[str, Any]] = field(default_factory=list)
    governance_by_app_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    state_by_app_key: dict[str, CandidateRecordStateDecision] = field(default_factory=dict)
    actionability: Actionability | None = None
    as_of: str = ""
    knowledge_version: str = PHASE1_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CANDIDATE_KNOWLEDGE_SCHEMA,
            "phase": self.knowledge_version,
            "candidate_ref": self.candidate_ref,
            "company_code": self.company_code,
            "anchor_app_key": self.anchor_app_key,
            "candidate_key": self.candidate_key,
            "application_count": len(self.applications),
            "applications": [
                {
                    "app_key": item.get("app_key"),
                    "company_code": item.get("company_code"),
                    "status": item.get("status"),
                    "position_code": item.get("position_code"),
                    "phone": item.get("phone"),
                }
                for item in self.applications
            ],
            "state_by_app_key": {key: value.to_dict() for key, value in self.state_by_app_key.items()},
            "actionability": self.actionability.to_dict() if self.actionability else None,
            "as_of": self.as_of,
            "knowledge_version": self.knowledge_version,
            "source_readers_executed": [],
        }


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_request_context(
    *,
    company_code: str | None,
    actor_user_id: str | None,
    permission_authority: str | None,
    permission_subject_user_id: str | None,
    permission_subject_company: str | None,
    permissions: list[str] | tuple[str, ...] | set[str] | None,
    modules_enabled: list[str] | tuple[str, ...] | set[str] | None = None,
    locale: str | None = None,
    request_id: str | None = None,
) -> CandidateKnowledgeRequestContext:
    return CandidateKnowledgeRequestContext(
        company_code=_norm(company_code).upper(),
        actor_user_id=_norm(actor_user_id),
        permission_authority=_norm(permission_authority),
        permission_subject_user_id=_norm(permission_subject_user_id),
        permission_subject_company=_norm(permission_subject_company).upper(),
        permissions=tuple(sorted({_norm(item) for item in (permissions or []) if _norm(item)})),
        modules_enabled=tuple(sorted({_norm(item) for item in (modules_enabled or []) if _norm(item)})),
        locale=_norm(locale) or None,
        request_id=_norm(request_id) or None,
    )


def authorize_request_context(
    context: CandidateKnowledgeRequestContext,
    *,
    module_enabled: ModuleEnabledFn | None = None,
) -> None:
    """Fail closed. Does not inherit tool-orchestrator empty-permission compatibility."""

    if not context.company_code:
        raise CandidateKnowledgeError(
            ERROR_TENANT_SCOPE_REQUIRED,
            "Candidate Knowledge requires a non-empty company_code.",
        )
    if not context.actor_user_id:
        raise CandidateKnowledgeError(
            ERROR_ACTOR_REQUIRED,
            "Candidate Knowledge requires an active actor identity.",
        )
    if context.permission_authority != REQUIRED_PERMISSION_AUTHORITY:
        raise CandidateKnowledgeError(
            ERROR_BACKEND_CURRENT_REQUIRED,
            "Candidate Knowledge requires permission_authority=backend_current.",
            reason_codes=(ERROR_BACKEND_CURRENT_REQUIRED, f"authority:{context.permission_authority or 'missing'}"),
        )
    if (
        not context.permission_subject_user_id
        or not context.permission_subject_company
        or context.permission_subject_user_id != context.actor_user_id
        or context.permission_subject_company != context.company_code
    ):
        raise CandidateKnowledgeError(
            ERROR_PERMISSION_SUBJECT_MISMATCH,
            "Permission subject must match the active actor and requested company.",
        )
    if not context.permissions:
        raise CandidateKnowledgeError(
            ERROR_PERMISSION_DENIED,
            "Empty permission contexts are denied.",
            reason_codes=(ERROR_PERMISSION_DENIED, "empty_permissions"),
        )
    if REQUIRED_PERMISSION not in context.permissions:
        raise CandidateKnowledgeError(
            ERROR_PERMISSION_DENIED,
            f"Missing required permission {REQUIRED_PERMISSION}.",
            reason_codes=(ERROR_PERMISSION_DENIED, f"missing:{REQUIRED_PERMISSION}"),
        )

    enabled = False
    if module_enabled is not None:
        try:
            enabled = bool(module_enabled(context.company_code, REQUIRED_MODULE))
        except Exception as exc:  # pragma: no cover - fail closed
            raise CandidateKnowledgeError(
                ERROR_MODULE_DISABLED,
                "Pre-hiring module entitlement check failed closed.",
                reason_codes=(ERROR_MODULE_DISABLED, "module_check_failed"),
            ) from exc
    else:
        enabled = REQUIRED_MODULE in context.modules_enabled
    if not enabled:
        raise CandidateKnowledgeError(
            ERROR_MODULE_DISABLED,
            "Pre-hiring module is not enabled for this company.",
        )


def parse_exact_candidate_ref(value: Any) -> str:
    """Parse exact app:<app_key> refs; optionally person:/subject: when Wave 4 ON.

    Names and bare keys remain rejected. Wave 1 app: compatibility is unchanged.
    """

    raw = _norm(value)
    if not raw:
        raise CandidateKnowledgeError(
            ERROR_INVALID_CANDIDATE_REF,
            "candidate_ref is required.",
        )
    if any(ch.isspace() for ch in raw):
        raise CandidateKnowledgeError(
            ERROR_INVALID_CANDIDATE_REF,
            "candidate_ref must be an exact app:<app_key> (or person:/subject:) value.",
        )

    # Wave 4 additive person:/subject: exact refs (flag default OFF).
    try:
        import candidate_knowledge_wave4 as ck_w4

        if ck_w4.enabled():
            kind, normalized = ck_w4.classify_knowledge_ref(raw)
            if kind in {"app", "person", "subject"}:
                return normalized
    except ValueError:
        pass
    except Exception:
        pass

    if not raw.startswith(CANDIDATE_REF_PREFIX):
        raise CandidateKnowledgeError(
            ERROR_CANDIDATE_AMBIGUOUS,
            "Name-only or non-app references are invalid for exact Candidate Knowledge reads.",
            reason_codes=(ERROR_CANDIDATE_AMBIGUOUS, ERROR_NAME_ONLY_INVALID, "name_or_non_app_ref"),
        )
    try:
        app_key = app_key_from_candidate_ref(raw)
    except ValueError as exc:
        raise CandidateKnowledgeError(
            ERROR_INVALID_CANDIDATE_REF,
            "candidate_ref must be app:<app_key>.",
        ) from exc
    if app_key.lower().startswith("name:"):
        raise CandidateKnowledgeError(
            ERROR_CANDIDATE_AMBIGUOUS,
            "Name-only references are invalid for exact Candidate Knowledge reads.",
            reason_codes=(ERROR_CANDIDATE_AMBIGUOUS, "name_ref"),
        )
    return candidate_ref_from_app_key(app_key)


def _candidate_key_from_application(application: dict[str, Any]) -> str:
    return _norm(application.get("phone"))


def _strictest_actionability(
    decisions: list[CandidateRecordStateDecision],
) -> Actionability:
    """AND actionability across siblings (legacy helper; not used for Job caps).

    Wave 1 exact reads use ``_anchor_actionability`` so a held sibling cannot
    over-deny contact/lifecycle/ranking for a valid live anchor application.
    """

    if not decisions:
        return Actionability(
            readable=False,
            contact_allowed=False,
            lifecycle_mutation_allowed=False,
            job_ranking_allowed=False,
            reason_codes=("no_applications",),
        )
    payloads = [item.to_actionability() for item in decisions]
    readable = all(bool(item["readable"]) for item in payloads) and any(
        item.get("read_projection") != "denied" for item in payloads
    )
    if any(item.get("read_projection") == "denied" for item in payloads):
        if all(item.get("read_projection") == "denied" for item in payloads):
            readable = False
        else:
            readable = True
    contact_allowed = all(bool(item["contact_allowed"]) for item in payloads)
    lifecycle = all(bool(item["lifecycle_mutation_allowed"]) for item in payloads)
    ranking = all(bool(item["job_ranking_allowed"]) for item in payloads)
    held_states = [item.get("held_state") for item in payloads if item.get("held_state")]
    reasons: list[str] = []
    for item in payloads:
        for code in item.get("reason_codes") or []:
            if code not in reasons:
                reasons.append(str(code))
    return Actionability(
        readable=readable,
        contact_allowed=contact_allowed and readable,
        lifecycle_mutation_allowed=lifecycle and readable,
        job_ranking_allowed=ranking and readable,
        held_state=str(held_states[0]) if held_states else None,
        reason_codes=tuple(reasons) or ("normal",),
    )


def _anchor_actionability(
    state_by_app: dict[str, CandidateRecordStateDecision],
    *,
    anchor_app_key: str,
) -> Actionability:
    """Job capabilities and subject readability for the exact anchor app only."""

    decision = state_by_app.get(anchor_app_key)
    if decision is None:
        return Actionability(
            readable=False,
            contact_allowed=False,
            lifecycle_mutation_allowed=False,
            job_ranking_allowed=False,
            reason_codes=("anchor_missing",),
        )
    payload = decision.to_actionability()
    return Actionability(
        readable=bool(payload.get("readable")),
        contact_allowed=bool(payload.get("contact_allowed")),
        lifecycle_mutation_allowed=bool(payload.get("lifecycle_mutation_allowed")),
        job_ranking_allowed=bool(payload.get("job_ranking_allowed")),
        held_state=payload.get("held_state"),
        reason_codes=tuple(payload.get("reason_codes") or ("normal",)),
    )


def _anchor_read_projection(resolved: Phase1ResolvedSubject) -> str:
    decision = resolved.state_by_app_key.get(resolved.anchor_app_key)
    if decision is None:
        return "denied"
    return str(decision.read_projection)


class CandidateKnowledgeAuthority:
    """Authorize → exact resolve → aggregate → Phase 2/3 section assembly."""

    def __init__(
        self,
        store: CandidateKnowledgeStore,
        *,
        module_enabled: ModuleEnabledFn | None = None,
    ) -> None:
        self._store = store
        self._module_enabled = module_enabled
        self._authorized = False
        self._resolved: Phase1ResolvedSubject | None = None
        self._mutations = 0
        self._readers_executed: list[str] = []

    @property
    def mutation_count(self) -> int:
        return self._mutations

    @property
    def readers_executed(self) -> tuple[str, ...]:
        return tuple(self._readers_executed)

    def authorize(self, context: CandidateKnowledgeRequestContext) -> CandidateKnowledgeRequestContext:
        authorize_request_context(context, module_enabled=self._module_enabled)
        self._authorized = True
        self._resolved = None
        self._readers_executed = []
        return context

    def resolve_exact(
        self,
        context: CandidateKnowledgeRequestContext,
        candidate_ref: Any,
    ) -> Phase1ResolvedSubject:
        self.authorize(context)
        exact_ref = parse_exact_candidate_ref(candidate_ref)

        # Wave 4: person:/subject: Talent Pool refs — searchable, non-actionable.
        try:
            import candidate_knowledge_wave4 as ck_w4

            if ck_w4.enabled():
                kind, normalized = ck_w4.classify_knowledge_ref(exact_ref)
                if kind in {"person", "subject"}:
                    provisional = kind == "subject"
                    actionability = ck_w4.talent_pool_actionability(
                        provisional=provisional,
                        held=True,
                        restricted=False,
                    )
                    resolved = Phase1ResolvedSubject(
                        candidate_ref=normalized,
                        company_code=context.company_code,
                        anchor_app_key="",
                        candidate_key=(
                            ck_w4.person_id_from_candidate_ref(normalized)
                            if kind == "person"
                            else ck_w4.subject_id_from_candidate_ref(normalized)
                        ),
                        applications=[],
                        governance_by_app_key={},
                        state_by_app_key={},
                        actionability=actionability,
                        as_of=_now_iso(),
                        knowledge_version=PHASE1_VERSION,
                    )
                    self._resolved = resolved
                    return resolved
        except Exception:
            pass

        app_key = app_key_from_candidate_ref(exact_ref)

        application = self._store.get_application(company_code=context.company_code, app_key=app_key)
        if not application:
            raise CandidateKnowledgeError(
                ERROR_CANDIDATE_NOT_FOUND,
                "Candidate was not found in this tenant.",
            )

        company = _norm(application.get("company_code")).upper()
        if company != context.company_code:
            raise CandidateKnowledgeError(
                ERROR_CANDIDATE_NOT_FOUND,
                "Candidate was not found in this tenant.",
            )

        candidate_key = _candidate_key_from_application(application)
        if not candidate_key:
            raise CandidateKnowledgeError(
                ERROR_CANDIDATE_NOT_FOUND,
                "Candidate was not found in this tenant.",
                reason_codes=(ERROR_CANDIDATE_NOT_FOUND, "missing_candidate_key"),
            )

        bound = self._store.list_bound_applications(
            company_code=context.company_code,
            candidate_key=candidate_key,
        )
        applications = [
            item
            for item in bound
            if isinstance(item, dict)
            and _norm(item.get("company_code")).upper() == context.company_code
            and _norm(item.get("phone")) == candidate_key
        ]
        if not any(_norm(item.get("app_key")) == app_key for item in applications):
            applications = [application, *applications]

        unique: dict[str, dict[str, Any]] = {}
        for item in applications:
            key = _norm(item.get("app_key"))
            if key and key not in unique:
                unique[key] = item
        applications = list(unique.values())
        applications.sort(key=lambda item: (_norm(item.get("app_key")),))

        governance_by_app: dict[str, dict[str, Any]] = {}
        state_by_app: dict[str, CandidateRecordStateDecision] = {}
        for item in applications:
            key = _norm(item.get("app_key"))
            gov = self._store.get_governance(company_code=context.company_code, app_key=key) or {}
            governance_by_app[key] = gov
            state_by_app[key] = evaluate_candidate_record_state(item, governance=gov)

        # Exact Job capabilities follow the anchor application. Sibling held
        # or restricted states remain visible in state_by_app_key but must not
        # over-deny a valid live app:<app_key> read.
        actionability = _anchor_actionability(state_by_app, anchor_app_key=app_key)
        anchor_decision = state_by_app.get(app_key)
        if (
            actionability.readable is False
            and anchor_decision is not None
            and (
                "deletion_completed" in anchor_decision.governance_flags
                or anchor_decision.read_projection == "denied"
            )
        ):
            raise CandidateKnowledgeError(
                ERROR_CANDIDATE_RESTRICTED,
                "Candidate knowledge is restricted for this subject.",
                reason_codes=(ERROR_CANDIDATE_RESTRICTED, *actionability.reason_codes),
            )

        resolved = Phase1ResolvedSubject(
            candidate_ref=exact_ref,
            company_code=context.company_code,
            anchor_app_key=app_key,
            candidate_key=candidate_key,
            applications=applications,
            governance_by_app_key=governance_by_app,
            state_by_app_key=state_by_app,
            actionability=actionability,
            as_of=_now_iso(),
            knowledge_version=PHASE1_VERSION,
        )
        self._resolved = resolved
        return resolved

    def resolve_name_only(self, context: CandidateKnowledgeRequestContext, name: Any) -> None:
        self.authorize(context)
        raise CandidateKnowledgeError(
            ERROR_CANDIDATE_AMBIGUOUS,
            "Name-only exact reads are ambiguous and do not bind or merge candidates.",
            reason_codes=(ERROR_CANDIDATE_AMBIGUOUS, "name_only", f"input:{_norm(name)[:64]}"),
        )

    def assert_source_reader_blocked(self, reader_name: str) -> None:
        """Fail closed for pre-resolution access and forbidden/Phase 4+ readers."""

        name = _norm(reader_name)
        if not self._authorized or self._resolved is None:
            raise CandidateKnowledgeError(
                ERROR_SOURCE_READER_BLOCKED,
                "Source readers cannot execute before authorization and exact resolution.",
                reason_codes=(ERROR_SOURCE_READER_BLOCKED, "pre_resolution", name),
            )
        if name in PHASE2_SECTIONS or name in PHASE3_SECTIONS:
            # Phase 2/3 readers are allowed only via assemble_phase2/3 after resolution.
            return
        raise CandidateKnowledgeError(
            ERROR_SOURCE_READER_BLOCKED,
            "Source reader is forbidden or outside Phase 3.",
            reason_codes=(ERROR_SOURCE_READER_BLOCKED, "phase_boundary", name),
        )

    def phase1_record_shell(self, resolved: Phase1ResolvedSubject) -> CandidateKnowledgeRecord:
        """Typed shell with no Phase 2/3 source-section payloads."""

        if resolved.actionability is None:
            raise CandidateKnowledgeError(
                ERROR_SOURCE_READER_BLOCKED,
                "Actionability is required before returning a knowledge shell.",
            )
        anchor = next(
            (item for item in resolved.applications if _norm(item.get("app_key")) == resolved.anchor_app_key),
            resolved.applications[0] if resolved.applications else {},
        )
        display_name = _norm(anchor.get("candidate_name") or anchor.get("name")) or None
        return CandidateKnowledgeRecord(
            candidate_ref=resolved.candidate_ref,
            company_code=resolved.company_code,
            as_of=resolved.as_of,
            knowledge_version=resolved.knowledge_version,
            subject=CandidateKnowledgeSubject(
                display_name=display_name,
                contact_email_present=False,
                contact_phone_present=False,
                contact_email=None,
                contact_phone=None,
                source="phase1_resolution_shell",
            ),
            governance={
                "by_app_key": dict(resolved.governance_by_app_key),
                "state_by_app_key": {
                    key: value.to_dict() for key, value in resolved.state_by_app_key.items()
                },
            },
            identity_state={"open_identity_review_resolves": False},
            applications=[
                {
                    "app_key": item.get("app_key"),
                    "company_code": item.get("company_code"),
                    "status": item.get("status"),
                    "position_code": item.get("position_code"),
                }
                for item in resolved.applications
            ],
            coverage=[
                CoverageItem(
                    section=section,
                    state="not_authorized",
                    reason_codes=("phase1_shell_only",),
                    note="Phase 1 shell does not execute source readers for this section.",
                )
                for section in (
                    "canonical_cv",
                    "effective_facts",
                    "classifications",
                    "screening_evidence",
                    "assessments",
                    "interviews",
                    "ranking_evaluations",
                    "notes",
                    "identity_state",
                )
            ],
            actionability=resolved.actionability,
        )

    def assemble_phase2(
        self,
        context: CandidateKnowledgeRequestContext,
        candidate_ref: Any,
        *,
        sections: tuple[str, ...] | list[str] | None = None,
    ) -> CandidateKnowledgeRecord:
        """Authorize, resolve, then populate Phase 2 canonical sections only."""

        resolved = self.resolve_exact(context, candidate_ref)
        requested = tuple(sections or ("canonical_cv", "effective_facts", "classifications"))
        for name in requested:
            if name not in PHASE2_SECTIONS:
                raise CandidateKnowledgeError(
                    ERROR_SOURCE_READER_BLOCKED,
                    f"Section {name} is outside Phase 2.",
                    reason_codes=(ERROR_SOURCE_READER_BLOCKED, "phase2_section_denied", name),
                )

        projection = _anchor_read_projection(resolved)
        evidence: list[EvidenceRef] = []
        coverage: list[CoverageItem] = []
        canonical_cv: dict[str, Any] = {}
        effective_facts: dict[str, Any] = {}
        classifications: dict[str, Any] = {}

        if "canonical_cv" in requested:
            section = read_canonical_cv(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                read_projection=projection,
            )
            self._readers_executed.append("canonical_cv")
            canonical_cv = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "effective_facts" in requested:
            section = read_effective_facts(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                read_projection=projection,
            )
            self._readers_executed.append("effective_facts")
            effective_facts = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "classifications" in requested:
            section = read_effective_classification(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                read_projection=projection,
            )
            self._readers_executed.append("classifications")
            classifications = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        for section_name in (
            "screening_evidence",
            "assessments",
            "interviews",
            "ranking_evaluations",
            "notes",
            "identity_state",
        ):
            coverage.append(
                CoverageItem(
                    section=section_name,
                    state="not_authorized",
                    reason_codes=("phase2_boundary",),
                    note="Phase 3+ reader not enabled in assemble_phase2.",
                )
            )

        if resolved.actionability is None:
            raise CandidateKnowledgeError(
                ERROR_SOURCE_READER_BLOCKED,
                "Actionability is required before returning a knowledge record.",
            )

        anchor = next(
            (item for item in resolved.applications if _norm(item.get("app_key")) == resolved.anchor_app_key),
            resolved.applications[0] if resolved.applications else {},
        )
        display_name = _norm(anchor.get("candidate_name") or anchor.get("name")) or None
        return CandidateKnowledgeRecord(
            candidate_ref=resolved.candidate_ref,
            company_code=resolved.company_code,
            as_of=_now_iso(),
            knowledge_version=PHASE2_VERSION,
            subject=CandidateKnowledgeSubject(
                display_name=display_name,
                contact_email_present=False,
                contact_phone_present=False,
                contact_email=None,
                contact_phone=None,
                source="phase2_canonical_assembly",
            ),
            governance={
                "by_app_key": dict(resolved.governance_by_app_key),
                "state_by_app_key": {
                    key: value.to_dict() for key, value in resolved.state_by_app_key.items()
                },
            },
            identity_state={"open_identity_review_resolves": False},
            canonical_cv=canonical_cv,
            effective_facts=effective_facts,
            classifications=classifications,
            applications=[
                {
                    "app_key": item.get("app_key"),
                    "company_code": item.get("company_code"),
                    "status": item.get("status"),
                    "position_code": item.get("position_code"),
                }
                for item in resolved.applications
            ],
            evidence_manifest=evidence,
            coverage=coverage,
            actionability=resolved.actionability,
        )

    def assemble_phase3(
        self,
        context: CandidateKnowledgeRequestContext,
        candidate_ref: Any,
        *,
        sections: tuple[str, ...] | list[str] | None = None,
        application_limit: int = 50,
        application_offset: int = 0,
        include_phase2: bool = True,
    ) -> CandidateKnowledgeRecord:
        """Authorize, resolve, then populate Phase 3 workflow sections (and Phase 2 by default)."""

        resolved = self.resolve_exact(context, candidate_ref)
        default_sections = tuple(sorted(PHASE3_SECTIONS))
        if include_phase2:
            default_sections = tuple(sorted(PHASE2_SECTIONS | PHASE3_SECTIONS))
        requested = tuple(sections or default_sections)
        allowed = PHASE2_SECTIONS | PHASE3_SECTIONS
        for name in requested:
            if name not in allowed:
                raise CandidateKnowledgeError(
                    ERROR_SOURCE_READER_BLOCKED,
                    f"Section {name} is outside Phase 3.",
                    reason_codes=(ERROR_SOURCE_READER_BLOCKED, "phase3_section_denied", name),
                )
            if name in FORBIDDEN_SOURCE_READER_NAMES:
                raise CandidateKnowledgeError(
                    ERROR_SOURCE_READER_BLOCKED,
                    f"Forbidden source reader {name}.",
                    reason_codes=(ERROR_SOURCE_READER_BLOCKED, "forbidden_source", name),
                )

        projection = _anchor_read_projection(resolved)
        evidence: list[EvidenceRef] = []
        coverage: list[CoverageItem] = []
        app_keys = [_norm(item.get("app_key")) for item in resolved.applications if _norm(item.get("app_key"))]

        canonical_cv: dict[str, Any] = {}
        effective_facts: dict[str, Any] = {}
        classifications: dict[str, Any] = {}
        applications_payload: list[dict[str, Any]] = []
        screening_payload: list[dict[str, Any]] = []
        assessments_payload: list[dict[str, Any]] = []
        interviews_payload: list[dict[str, Any]] = []
        ranking_payload: list[dict[str, Any]] = []
        notes_payload: list[dict[str, Any]] = []
        identity_payload: dict[str, Any] = {"open_identity_review_resolves": False}

        if "canonical_cv" in requested:
            section = read_canonical_cv(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                read_projection=projection,
            )
            self._readers_executed.append("canonical_cv")
            canonical_cv = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "effective_facts" in requested:
            section = read_effective_facts(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                read_projection=projection,
            )
            self._readers_executed.append("effective_facts")
            effective_facts = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "classifications" in requested:
            section = read_effective_classification(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                read_projection=projection,
            )
            self._readers_executed.append("classifications")
            classifications = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "applications" in requested:
            section = read_applications(
                self._store,
                company_code=resolved.company_code,
                applications=resolved.applications,
                governance_by_app_key=resolved.governance_by_app_key,
                read_projection=projection,
                limit=application_limit,
                offset=application_offset,
            )
            self._readers_executed.append("applications")
            applications_payload = list(section.payload.get("items") or [])
            coverage.append(section.coverage)
            evidence.extend(section.evidence)
        else:
            applications_payload = [
                {
                    "app_key": item.get("app_key"),
                    "company_code": item.get("company_code"),
                    "status": item.get("status"),
                    "position_code": item.get("position_code"),
                }
                for item in resolved.applications
            ]

        if "screening_evidence" in requested:
            section = read_screening_evidence(
                self._store,
                company_code=resolved.company_code,
                app_keys=app_keys,
                read_projection=projection,
            )
            self._readers_executed.append("screening_evidence")
            screening_payload = list(section.payload.get("items") or [])
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "assessments" in requested:
            section = read_assessments(
                self._store,
                company_code=resolved.company_code,
                app_keys=app_keys,
                modules_enabled=context.modules_enabled,
                module_enabled=self._module_enabled,
                read_projection=projection,
            )
            self._readers_executed.append("assessments")
            assessments_payload = list(section.payload.get("items") or [])
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "interviews" in requested:
            section = read_interviews(
                self._store,
                company_code=resolved.company_code,
                app_keys=app_keys,
                modules_enabled=context.modules_enabled,
                module_enabled=self._module_enabled,
                read_projection=projection,
            )
            self._readers_executed.append("interviews")
            interviews_payload = list(section.payload.get("items") or [])
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "ranking_evaluations" in requested:
            section = read_ranking_evaluations(
                self._store,
                company_code=resolved.company_code,
                app_keys=app_keys,
                read_projection=projection,
            )
            self._readers_executed.append("ranking_evaluations")
            ranking_payload = list(section.payload.get("items") or [])
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "identity_state" in requested:
            section = read_identity_state(
                self._store,
                company_code=resolved.company_code,
                app_key=resolved.anchor_app_key,
                candidate_phone=resolved.candidate_key,
                permissions=context.permissions,
                read_projection=projection,
            )
            self._readers_executed.append("identity_state")
            identity_payload = section.payload
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if "notes" in requested:
            section = read_notes(
                self._store,
                company_code=resolved.company_code,
                app_keys=app_keys,
                candidate_phone=resolved.candidate_key,
                permissions=context.permissions,
                interviews_payload=interviews_payload,
                read_projection=projection,
            )
            self._readers_executed.append("notes")
            notes_payload = list(section.payload.get("items") or [])
            coverage.append(section.coverage)
            evidence.extend(section.evidence)

        if resolved.actionability is None:
            raise CandidateKnowledgeError(
                ERROR_SOURCE_READER_BLOCKED,
                "Actionability is required before returning a knowledge record.",
            )

        anchor = next(
            (item for item in resolved.applications if _norm(item.get("app_key")) == resolved.anchor_app_key),
            resolved.applications[0] if resolved.applications else {},
        )
        display_name = _norm(anchor.get("candidate_name") or anchor.get("name")) or None
        return CandidateKnowledgeRecord(
            candidate_ref=resolved.candidate_ref,
            company_code=resolved.company_code,
            as_of=_now_iso(),
            knowledge_version=PHASE3_VERSION,
            subject=CandidateKnowledgeSubject(
                display_name=display_name,
                contact_email_present=False,
                contact_phone_present=False,
                contact_email=None,
                contact_phone=None,
                source="phase3_history_assembly",
            ),
            governance={
                "by_app_key": dict(resolved.governance_by_app_key),
                "state_by_app_key": {
                    key: value.to_dict() for key, value in resolved.state_by_app_key.items()
                },
            },
            identity_state=identity_payload,
            canonical_cv=canonical_cv,
            effective_facts=effective_facts,
            classifications=classifications,
            applications=applications_payload,
            screening_evidence=screening_payload,
            assessments=assessments_payload,
            interviews=interviews_payload,
            ranking_evaluations=ranking_payload,
            notes=notes_payload,
            evidence_manifest=evidence,
            coverage=coverage,
            actionability=resolved.actionability,
        )


__all__ = [
    "CandidateKnowledgeAuthority",
    "CandidateKnowledgeRequestContext",
    "CandidateKnowledgeStore",
    "InMemoryCandidateKnowledgeStore",
    "PostgresCandidateKnowledgeStore",
    "PHASE1_VERSION",
    "PHASE2_VERSION",
    "PHASE3_VERSION",
    "PHASE2_SECTIONS",
    "PHASE3_SECTIONS",
    "Phase1ResolvedSubject",
    "authorize_request_context",
    "build_request_context",
    "parse_exact_candidate_ref",
]
