# Shifts Wave 3B — local coded preview

This preview is isolated from the dashboard build and is not deployed.

Open:

```text
ops/previews/shifts-wave3b/index.html?lang=en
ops/previews/shifts-wave3b/index.html?lang=ar
```

Optional query parameters:

- `drawer=create`
- `drawer=edit`
- `surface=requests`
- `surface=planning`

The fixture intentionally includes:

- identity anchored once per employee row
- dense and split schedules
- true overlap lanes
- conflict, reconciliation, cancelled, and healthy states
- overnight start and continuation fragments
- long Arabic names and labels
- desktop end-sheet and mobile full-screen drawer
- quieter Requests and Planning compositions

Screenshots are under `screenshots/`.

This artifact is a visual review gate only. It does not change scheduling logic,
permissions, mutation behavior, production assets, or backend contracts.

