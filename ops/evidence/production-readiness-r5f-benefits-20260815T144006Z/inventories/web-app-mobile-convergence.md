# R5F web / app convergence

- HR Web and Employee App read the same C3 tables through `benefits_surfaces`.
- Employee elect uses the same `elect_or_waive` authority as HR; only HR can confirm coverage.
- Employee workspace strips HR admin keys. Sensitive member/contribution fields are permission-stripped on HR reads without `benefits.sensitive`.
- HR Mobile admin and Manager workspace are not part of R5F.
- Home tile `/benefits` is entitlement-composed; no Benefits tab.
