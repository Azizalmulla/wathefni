# Expansion flows (not in default smoke suite)
# These are scaffolding for the full release matrix. They intentionally assert
# structure only after authenticated navigation exists — wire credentials +
# fixtures before promoting a flow into the smoke gate.

# Leave approve/reject, attendance correction, shift swap, onboarding accept/waive,
# document review, HR tasks, hiring/candidates/interviews, assistant, files,
# keyboard/modals, deep links, EN/AR/RTL, module-off, HR↔Employee switch:
# add one YAML per path under this folder, then register in run-release-gate.py
# SUITE=full selection.
