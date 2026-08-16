import React, { useState } from "react";

type Risk = {
  level: "P0" | "P1" | "P2";
  title: string;
  evidence: string;
  consequence: string;
};

const truth = [
  ["Attendance records", "42", "100% demo_seed=wathefni_v1"],
  ["Employees represented", "3 / 4", "No current operating coverage"],
  ["Records in last 30 days", "0", "Latest record: 9 Jun 2026"],
  ["Punch rows with Kuwait-time mismatch", "40 / 40", "08:58Z displays as 11:58 Kuwait"],
  ["Rows linked to shifts", "0 / 42", "All shift_id values are null"],
  ["Attendance events", "0", "No production punch/correction audit trail"],
  ["Device mappings / import batches", "0 / 0", "Import flag is off"],
  ["Active manager scopes", "0", "No production manager workflow configured"],
  ["Shift assignments", "23", "20 scheduled, 3 cancelled; 3 future"],
  ["Payroll timesheets", "2", "Both draft; both carry zero worked minutes"],
];

const risks: Risk[] = [
  {
    level: "P0",
    title: "Mutable day row is incorrectly acting as punch authority",
    evidence:
      "check-in, check-out, corrections, imports, leave effects and absence scanning directly update attendance_records. There is no immutable source-event authority, row_version or compare-and-swap.",
    consequence:
      "A retry, concurrent action or later correction can silently replace the fact used by payroll.",
  },
  {
    level: "P0",
    title: "Overnight and day-boundary calculations are wrong",
    evidence:
      "The 22:00–06:00 scheduled-minutes probe returns 0. Early leave at 05:00 returns 0 instead of 60, and post-midnight self checkout defaults to the new calendar day.",
    consequence:
      "Night workers can receive wrong totals, wrong day assignment, missed checkout, absence and overtime decisions.",
  },
  {
    level: "P0",
    title: "Production data cannot prove real operation",
    evidence:
      "All 42 rows are demo data; no rows exist in the last 30 days, no attendance events or audit actions exist, and 40 punched rows conflict with Kuwait-time interpretation.",
    consequence:
      "The enabled module has no trustworthy production truth or customer qualification basis.",
  },
  {
    level: "P0",
    title: "Payroll consumes unapproved mutable attendance",
    evidence:
      "Payroll sums every attendance row in-period, then computes overtime as aggregate worked minus aggregate scheduled. Attendance has no approved state and breaks do not exist.",
    consequence:
      "Draft timesheets can embed incorrect worked, absence and overtime minutes.",
  },
  {
    level: "P1",
    title: "Concurrency and idempotency are incomplete",
    evidence:
      "The upsert is SELECT then UPDATE/INSERT without row locking. The unique key includes nullable shift_id, so concurrent no-shift rows are not protected by PostgreSQL uniqueness.",
    consequence:
      "Duplicate employee-days and last-writer-wins check-in/check-out replacement remain possible.",
  },
  {
    level: "P1",
    title: "No sessions, breaks, missing-punch workflow or dispute lifecycle",
    evidence:
      "The schema has day rows and events only. Missing punches are an import issue code, not a reviewable state. Corrections overwrite the row rather than request → approve/reject.",
    consequence:
      "Operational exceptions cannot be resolved with durable ownership, evidence or dual control.",
  },
  {
    level: "P1",
    title: "Acquisition channels are mostly absent or dark",
    evidence:
      "Employee app is read-only. There is no kiosk, QR or GPS path. Device import is off, with zero device mappings, and the existing device-binding API is not reachable from the UI. WhatsApp is the only active self-clock path.",
    consequence:
      "Attendance cannot yet serve as a dependable workplace clocking system.",
  },
  {
    level: "P1",
    title: "Corrections can be lost and exception queues are incomplete",
    evidence:
      "Manual correction does not stamp the manual_edit marker used by leave reversal, so a corrected leave-derived row can later be deleted. HR mobile labels its list as exceptions but fetches all attendance rows; its home queue includes late records but omits absences.",
    consequence:
      "An authorized correction can disappear, while operators receive a misleading or incomplete review queue.",
  },
  {
    level: "P1",
    title: "Manager scope exists in code but not in production",
    evidence:
      "Manager role fails closed when unconfigured, but production has zero manager users, scopes and org assignments. There is also no explicit manager-self correction exclusion.",
    consequence:
      "Manager operation is unproven and self-correction remains an authorization gap when scopes are later configured.",
  },
  {
    level: "P2",
    title: "Status and localization contracts diverge",
    evidence:
      "Employee summary counts present/late/absent but ignores completed, approved_leave and incomplete. Web Attendance is hard-coded English with a wide scrolling table; employee and HR mobile have EN/AR RTL foundations.",
    consequence:
      "Users can see inconsistent counts and Arabic web users do not receive a complete operational surface.",
  },
];

const permissionRows = [
  {
    actor: "Employee · WhatsApp",
    read: "Self only",
    clock: "Self check-in/out; shift required",
    correct: "No",
    scope: "Phone → employee + company module",
    gap: "No device/location attestation; overnight checkout fails",
  },
  {
    actor: "Employee app · Talal allowlist",
    read: "Self · last 30 days",
    clock: "No",
    correct: "No",
    scope: "Authenticated employee, tenant + feature",
    gap: "Read-only; status summary drops valid states",
  },
  {
    actor: "Viewer",
    read: "Company-wide",
    clock: "No",
    correct: "No",
    scope: "Tenant + attendance.read",
    gap: "Read is intentionally broad inside tenant",
  },
  {
    actor: "Team manager",
    read: "Assigned scope",
    clock: "Manage permission exists",
    correct: "Yes, with confirmation",
    scope: "Explicit branch/team/direct/company; fail closed",
    gap: "No production scopes; no self-exclusion",
  },
  {
    actor: "HR / owner",
    read: "Company-wide",
    clock: "Can invoke registered clock actions",
    correct: "Direct correction / mark absent",
    scope: "Tenant + attendance.manage",
    gap: "No second-party approval or row version",
  },
  {
    actor: "System absence scan",
    read: "Scheduled shifts",
    clock: "Writes absence / approved leave",
    correct: "Automatic",
    scope: "Internal auth + module gate",
    gap: "Shares the same mutable row authority",
  },
  {
    actor: "Device import operator",
    read: "Tenant batch preview",
    clock: "CSV/XLSX punch import",
    correct: "Commit / reverse",
    scope: "Flag + attendance.manage + company",
    gap: "Off in prod; bind API has no UI; re-upload lacks source-file idempotency",
  },
];

const phases = [
  {
    name: "Wave 1 · Authority foundation",
    text: "Introduce an immutable punch ledger, deterministic Kuwait/overnight projector, versioned attendance-day projection, correction request lifecycle and payroll-approved snapshot boundary. Route existing writers through one service while preserving read API compatibility. Keep all new writes dark until qualification.",
  },
  {
    name: "Wave 2 · Controlled acquisition",
    text: "Qualify one source at a time: signed device import first, then employee self-clock. Add source-event idempotency, device binding controls, duplicate/missing-punch queues and synthetic production canaries.",
  },
  {
    name: "Wave 3 · Manager and HR operation",
    text: "Configure org scopes, block self-resolution, prove correction approvals and disputes, and expose exception ownership. No broad rollout until cross-tenant and concurrency qualification passes.",
  },
  {
    name: "Wave 4 · UX and payroll qualification",
    text: "Only after authority is stable: complete EN/AR/RTL web and mobile exception flows, reconcile every day/session/break total, qualify payroll locks/export, then decide controlled GO.",
  },
];

const stateNodes = [
  ["Captured", "Immutable punch accepted with tenant, employee, UTC instant, source and idempotency key"],
  ["Attributed", "Punch assigned to a shift/work day using company timezone and overnight window"],
  ["Incomplete", "Missing in/out or ambiguous sequence; excluded from payroll authority"],
  ["Calculated", "Sessions, unpaid breaks and day totals deterministically projected"],
  ["Needs review", "Late, early leave, absence, overtime or manual correction pending"],
  ["Approved", "Authorized reviewer locks the attendance-day version"],
  ["Exported", "Payroll consumes an immutable approved snapshot"],
  ["Disputed", "Employee/manager dispute opens a new version; prior approval remains auditable"],
];

const colors = {
  bg: "#08111f",
  panel: "#101d2f",
  panel2: "#14243a",
  text: "#ecf3ff",
  muted: "#9eb0c8",
  line: "#29405d",
  cyan: "#54d7e4",
  green: "#62d394",
  amber: "#ffc861",
  red: "#ff737d",
};

function Pill({ children, tone = "cyan" }: { children: React.ReactNode; tone?: "cyan" | "green" | "amber" | "red" }) {
  const map = { cyan: colors.cyan, green: colors.green, amber: colors.amber, red: colors.red };
  return (
    <span style={{ border: `1px solid ${map[tone]}66`, color: map[tone], borderRadius: 999, padding: "5px 10px", fontSize: 12, fontWeight: 800, letterSpacing: 0.5 }}>
      {children}
    </span>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <section style={{ background: colors.panel, border: `1px solid ${colors.line}`, borderRadius: 18, padding: 20, boxShadow: "0 16px 45px rgba(0,0,0,.18)", ...style }}>
      {children}
    </section>
  );
}

function SectionTitle({ children, note }: { children: React.ReactNode; note?: string }) {
  return (
    <div style={{ marginBottom: 15 }}>
      <h2 style={{ margin: 0, fontSize: 19, color: colors.text }}>{children}</h2>
      {note ? <div style={{ color: colors.muted, fontSize: 13, marginTop: 5 }}>{note}</div> : null}
    </div>
  );
}

function Overview() {
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 12 }}>
        {[
          ["Verdict", "NO-GO", colors.red],
          ["Real recent rows", "0", colors.red],
          ["Audited events", "0", colors.red],
          ["Current utility", "Read/export demo", colors.amber],
        ].map(([label, value, color]) => (
          <Card key={label} style={{ padding: 17 }}>
            <div style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 0.9 }}>{label}</div>
            <div style={{ color, fontSize: 24, fontWeight: 900, marginTop: 6 }}>{value}</div>
          </Card>
        ))}
      </div>

      <Card>
        <SectionTitle note="Read-only production snapshot, 2 Aug 2026">Production truth</SectionTitle>
        <div style={{ display: "grid", gap: 8 }}>
          {truth.map(([name, value, note]) => (
            <div key={name} style={{ display: "grid", gridTemplateColumns: "minmax(190px,1.2fr) 90px minmax(220px,2fr)", gap: 12, alignItems: "center", background: colors.panel2, borderRadius: 12, padding: "11px 13px" }}>
              <strong style={{ color: colors.text, fontSize: 13 }}>{name}</strong>
              <span style={{ color: colors.cyan, fontSize: 16, fontWeight: 900 }}>{value}</span>
              <span style={{ color: colors.muted, fontSize: 12 }}>{note}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <SectionTitle note="Current data flow; red arrows terminate at a mutable authority">Architecture and authority</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 48px 1.15fr 48px 1fr", gap: 8, alignItems: "stretch" }}>
          <FlowColumn title="Capture paths" items={["Employee WhatsApp", "HR/manager registry action", "HR mobile confirmation", "Device file import · OFF", "Leave / absence scan"]} />
          <Arrow />
          <FlowColumn title="Current authority" danger items={["attendance_records", "One mutable employee-day row", "check_in_at / check_out_at", "status / late / early", "No sessions, breaks or row version"]} />
          <Arrow />
          <FlowColumn title="Consumers" items={["Dashboard + CSV", "HR mobile exceptions", "Employee app summary", "Analytics", "Payroll provisional totals"]} />
        </div>
        <div style={{ marginTop: 13, color: colors.muted, fontSize: 12 }}>
          attendance_events is intended as history, but production contains zero rows and ordinary updates do not use it as canonical replay authority.
        </div>
      </Card>
    </div>
  );
}

function FlowColumn({ title, items, danger }: { title: string; items: string[]; danger?: boolean }) {
  return (
    <div style={{ background: danger ? "#321b27" : colors.panel2, border: `1px solid ${danger ? colors.red + "66" : colors.line}`, borderRadius: 14, padding: 15 }}>
      <div style={{ color: danger ? colors.red : colors.cyan, fontWeight: 900, marginBottom: 10 }}>{title}</div>
      {items.map((item) => <div key={item} style={{ color: colors.text, fontSize: 12, padding: "6px 0", borderBottom: `1px solid ${colors.line}66` }}>{item}</div>)}
    </div>
  );
}

function Arrow() {
  return <div style={{ alignSelf: "center", color: colors.amber, textAlign: "center", fontSize: 28 }}>→</div>;
}

function Risks() {
  return (
    <Card>
      <SectionTitle note="Ranked by payroll/data-integrity impact, not visual polish">Critical risks</SectionTitle>
      <div style={{ display: "grid", gap: 11 }}>
        {risks.map((risk) => {
          const tone = risk.level === "P0" ? "red" : risk.level === "P1" ? "amber" : "cyan";
          return (
            <div key={risk.title} style={{ background: colors.panel2, borderRadius: 14, padding: 15, borderLeft: `4px solid ${risk.level === "P0" ? colors.red : risk.level === "P1" ? colors.amber : colors.cyan}` }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Pill tone={tone}>{risk.level}</Pill>
                <strong style={{ color: colors.text }}>{risk.title}</strong>
              </div>
              <p style={{ color: colors.muted, margin: "10px 0 5px", fontSize: 13, lineHeight: 1.55 }}>{risk.evidence}</p>
              <p style={{ color: colors.text, margin: 0, fontSize: 12, lineHeight: 1.5 }}><b>Impact:</b> {risk.consequence}</p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function Ownership() {
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <Card>
        <SectionTitle note="Current effective ownership and missing boundaries">Permission matrix</SectionTitle>
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 930 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1.15fr .8fr 1.1fr 1.05fr 1.3fr 1.7fr", color: colors.muted, fontSize: 11, textTransform: "uppercase", letterSpacing: .7, padding: "0 10px 8px" }}>
              {["Actor", "Read", "Clock", "Correct", "Scope", "Gap"].map(x => <b key={x}>{x}</b>)}
            </div>
            {permissionRows.map((row) => (
              <div key={row.actor} style={{ display: "grid", gridTemplateColumns: "1.15fr .8fr 1.1fr 1.05fr 1.3fr 1.7fr", gap: 10, background: colors.panel2, borderRadius: 11, padding: 11, marginBottom: 7, color: colors.text, fontSize: 12, lineHeight: 1.4 }}>
                <b>{row.actor}</b><span>{row.read}</span><span>{row.clock}</span><span>{row.correct}</span><span>{row.scope}</span><span style={{ color: colors.amber }}>{row.gap}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <Card>
        <SectionTitle note="Target lifecycle required before payroll authority">Attendance state model</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 10 }}>
          {stateNodes.map(([name, text], index) => (
            <div key={name} style={{ background: colors.panel2, border: `1px solid ${index >= 5 ? colors.green + "55" : colors.line}`, borderRadius: 14, padding: 14 }}>
              <div style={{ color: index >= 5 ? colors.green : colors.cyan, fontWeight: 900 }}>{index + 1}. {name}</div>
              <div style={{ color: colors.muted, fontSize: 12, lineHeight: 1.5, marginTop: 7 }}>{text}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Plan() {
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <Card>
        <SectionTitle note="No UI redesign or feature rollout in the first wave">Recommended phased plan</SectionTitle>
        <div style={{ display: "grid", gap: 10 }}>
          {phases.map((phase, index) => (
            <div key={phase.name} style={{ display: "grid", gridTemplateColumns: "48px 1fr", gap: 12, background: colors.panel2, borderRadius: 14, padding: 14 }}>
              <div style={{ width: 38, height: 38, borderRadius: 12, background: index === 0 ? colors.red : colors.line, display: "grid", placeItems: "center", fontWeight: 900, color: colors.text }}>{index + 1}</div>
              <div>
                <strong style={{ color: index === 0 ? colors.red : colors.text }}>{phase.name}</strong>
                <div style={{ color: colors.muted, fontSize: 13, lineHeight: 1.55, marginTop: 5 }}>{phase.text}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card style={{ borderColor: colors.red + "77" }}>
        <SectionTitle note="The exact next implementation scope">Wave 1 exit contract</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 10 }}>
          {[
            "Append-only punch IDs are unique per tenant + source + source event.",
            "Kuwait work-day attribution passes normal, overnight and no-shift cases.",
            "Day/session/break totals are reproducible from immutable inputs.",
            "Corrections use request → approve/reject with row version and no self-approval.",
            "Existing WhatsApp, import and system writers call one authority service.",
            "Payroll reads only approved versioned snapshots; draft totals reconcile exactly.",
            "Cross-tenant, manager-scope and concurrent-write tests fail closed.",
            "Synthetic production canary proves capture → review → approval → payroll preview → cleanup.",
          ].map((item) => (
            <div key={item} style={{ background: colors.panel2, borderRadius: 12, padding: 13, color: colors.text, fontSize: 12, lineHeight: 1.5 }}>
              <span style={{ color: colors.green, fontWeight: 900, marginRight: 8 }}>✓</span>{item}
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <SectionTitle>Keep / move / rebuild</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
          <Decision title="Keep" tone={colors.green} items={["Tenant and manager-scope gates", "Shift-aware import parser", "Biometric-column dropping", "Import locked-period reverse guard", "Read/export API compatibility", "Approved timesheet/export boundary"]} />
          <Decision title="Move" tone={colors.amber} items={["Raw punches → immutable ledger", "Day totals → deterministic projection", "Manual changes → correction requests", "Payroll input → approved snapshots", "Device binding → import remediation flow", "Source identity → typed adapter metadata"]} />
          <Decision title="Rebuild" tone={colors.red} items={["Overnight calculations", "Idempotent capture service", "Sessions and unpaid breaks", "Missing-punch review queue", "True HR mobile exception filtering", "Self-approval boundary", "Web EN/AR/RTL after authority"]} />
        </div>
      </Card>
    </div>
  );
}

function Decision({ title, tone, items }: { title: string; tone: string; items: string[] }) {
  return (
    <div style={{ background: colors.panel2, borderRadius: 14, padding: 15, borderTop: `3px solid ${tone}` }}>
      <strong style={{ color: tone }}>{title}</strong>
      {items.map(item => <div key={item} style={{ color: colors.text, fontSize: 12, marginTop: 9 }}>• {item}</div>)}
    </div>
  );
}

export default function AttendanceWave0Audit() {
  const [tab, setTab] = useState<"overview" | "risks" | "ownership" | "plan">("overview");
  const tabs = [
    ["overview", "Production truth"],
    ["risks", "Risks"],
    ["ownership", "State & permissions"],
    ["plan", "Plan"],
  ] as const;
  return (
    <main style={{ minHeight: "100vh", background: `radial-gradient(circle at 85% 0%, #163b4a 0, ${colors.bg} 35%)`, color: colors.text, fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", padding: "30px clamp(18px,4vw,58px) 60px" }}>
      <header style={{ maxWidth: 1180, margin: "0 auto 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Pill tone="red">NO-GO</Pill>
          <Pill>Attendance Wave 0</Pill>
          <span style={{ color: colors.muted, fontSize: 12 }}>Production truth & architecture audit · 2 Aug 2026</span>
        </div>
        <h1 style={{ fontSize: "clamp(30px,5vw,54px)", lineHeight: 1.04, margin: "15px 0 10px", letterSpacing: -1.7 }}>Useful read surface.<br /><span style={{ color: colors.red }}>Unsafe time authority.</span></h1>
        <p style={{ color: colors.muted, maxWidth: 850, fontSize: 15, lineHeight: 1.6, margin: 0 }}>
          The module can display and export rows, but it cannot yet be trusted for real clocking, corrections, attendance totals or payroll. The first implementation wave must establish immutable authority and deterministic calculations—not redesign the UI.
        </p>
        <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 21 }}>
          {tabs.map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} style={{ cursor: "pointer", border: `1px solid ${tab === key ? colors.cyan : colors.line}`, background: tab === key ? "#17354b" : colors.panel, color: tab === key ? colors.cyan : colors.muted, borderRadius: 999, padding: "9px 14px", fontWeight: 800, fontSize: 12 }}>
              {label}
            </button>
          ))}
        </nav>
      </header>
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        {tab === "overview" ? <Overview /> : tab === "risks" ? <Risks /> : tab === "ownership" ? <Ownership /> : <Plan />}
      </div>
      <footer style={{ maxWidth: 1180, margin: "24px auto 0", color: colors.muted, fontSize: 11, lineHeight: 1.6 }}>
        Evidence: read-only production database/process/systemd inspection; app.py attendance, scope, mobile and payroll paths; attendance_import.py; dashboard, employee-mobile and HR-mobile clients; attendance/payroll smoke harnesses. No code, data, flags or deployments were changed.
      </footer>
    </main>
  );
}
