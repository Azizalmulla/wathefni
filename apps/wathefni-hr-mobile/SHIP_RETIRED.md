# Wathefni HR mobile — SHIP RETIRED

**Status:** Not a public ship target (effective 2026-08-09)

This package remains as **legacy source / fixture preview** only.

## What shipped instead

HR operator experience is integrated into the public **Wathefni** app
(`apps/wathefni-employee-mobile`, bundle `ai.wathefni.employee`) as an isolated
`/hr/*` workspace with a separate operator SecureStore namespace
(`wathefni.hr.*`) and `/dashboard/mobile/*` API allowlist.

## Do not

- create EAS production / TestFlight builds for `ai.wathefni.hr`
- configure OTA updates for this package
- treat this app as a second App Store listing

## Allowed

- keep design-preview / contract tests for historical HR-2/HR-3 fixtures
- use as reference while porting screens into `wathefni-employee-mobile/src/hr`
