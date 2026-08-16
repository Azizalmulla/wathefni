# Employee App — Legacy Wathefni logo audit

**Stamp:** `20260809T062852Z`  
**Verdict:** **PASS**

## Canonical source (only active badge)

| | |
|---|---|
| Path | `apps/wathefni-employee-mobile/assets/brand/wathefni-app-icon-approved-master.png` |
| SHA-256 | `85884e9b75fb3478ac788e536c88d02a8f06d83715deb4ab904028922a24c231` |
| Production copies | `assets/icon.png` · `assets/adaptive-icon.png` (**byte-identical**) |

Badge geometry / cream / black mark were **not** redrawn.

## Every occurrence found

| Location | What it was | Action |
|---|---|---|
| `assets/icon.png` | Approved master (already locked) | Keep (= master) |
| `assets/adaptive-icon.png` | Approved master (already locked) | Keep (= master) |
| `assets/notification-icon.png` | White 96px glyph from master | Keep (scale+threshold only) |
| `assets/splash.png` | **Legacy** circular serif **W** + “Wathefni” wordmark on cream | **Replaced** — cream `#F8F2E8` canvas + centered **scaled** master (no crop/redraw) |
| `assets/brand/wathefni-app-icon-source.png` | Duplicate of master | **Removed** (unreferenced) |
| `assets/brand/icon-previews/*` | Extraction/pipeline previews (`extracted-mark`, bottom-anchor experiments, etc.) | **Removed** (unreferenced) |
| `assets/brand/_audit-splash-legacy-crop.png` | Temp audit crop | **Removed** |
| In-app `Wordmark` | Typography-only “Wathefni” text | Keep (design system; not a PNG logo) |
| In-app `WathefniBloom` | Decorative pastel shapes | Keep (not a logo mark) |
| `docs/phase9a2-preview/*.png` | Historical screenshots (docs only) | Left (not shipped native assets) |
| Dashboard `favicon.svg` | Separate web app | Out of Employee App scope |
| Orchestrator email HTML logos | None found as Wathefni badge PNGs in this pass | N/A |
| Android monochrome / extra mipmaps | None in app sources (only RN template under `node_modules`) | N/A |

## Replaced / removed

**Replaced**
- `assets/splash.png` ← was legacy serif-W circle lockup; now approved badge scaled onto splash cream

**Archived (not shipped)**
- `assets/brand/legacy/splash-legacy-serif-W-circle.png`

**Removed (unused)**
- `assets/brand/wathefni-app-icon-source.png`
- entire `assets/brand/icon-previews/` directory
- audit temp crops

## One active brand mark confirmation

Shipped native brand images that depict the Wathefni **badge**:

1. `icon.png` = master  
2. `adaptive-icon.png` = master  
3. `splash.png` = master composited (scaled) on cream  
4. `notification-icon.png` = monochrome derivative of master  

No second badge geometry remains in the Employee App native asset pipeline.

## Native rebuild

Splash/icon are native — new iOS/Android production builds started with this audit (see evidence `*-build.txt`).

## Native builds

| iOS | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/17092f6e-5345-42c4-ab44-9bb972b33c82 |
| Android | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/0ec1359b-a867-4bcc-8736-016dfce21412 |
