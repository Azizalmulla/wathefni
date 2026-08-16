# Permission and rollout matrix (Wave 6A)

## Permission matrix (from module)
```
{'create_rotation_pattern': ['hr', 'admin'], 'assign_rotation': ['hr', 'admin'], 'preview_rotation': ['hr', 'admin', 'manager_scoped'], 'generate_draft_from_rotation': ['hr', 'admin'], 'manage_compliance_profile': ['hr', 'admin'], 'export_pam': ['hr', 'admin'], 'real_mutation_requires': ['permission_and_scope', 'allowlist', 'audit_reason', 'concurrency_token', 'policy_conflict_evaluation', 'kill_switch']}
```

## Prepared but NOT enabled
- Named HR allowlist
- Named scoped-manager allowlist
- Talal read-only schedule view (still read-only)
- Real reminders / job timers
- Controlled employee open-shift claims

## Real mutation requirements (when later enabled)
permission + scope · allowlist · audit reason · concurrency token · policy/conflict evaluation · kill-switch
