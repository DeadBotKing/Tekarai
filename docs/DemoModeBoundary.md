# The boundary between Demo Mode and Production

## Why this document exists

Demo mode stopped being a mode. It became 151 `if (runtimeConfig.demoMode)`
branches scattered across 35 source files, and the line between "fake data for
a sales call" and "a real deployment holding real tenant data" was a single
environment variable. This document records what was wrong, what is now
enforced, and what debt is still outstanding.

## What was wrong

1. **A production build could be talked into demo mode.** `runtimeConfig.demoMode`
   was read from `VITE_DEMO_MODE` with no regard for the build target.
2. **Demo mode includes an authentication bypass.** `demoLogin` in
   `src/features/demo/demoData.ts` ignores the submitted credentials entirely
   and returns `role: "Platform Administrator"` with `permissions: ["*"]`.
   Combined with (1), one stray variable in a CI environment is the difference
   between a deployment and a deployment that lets anybody in as administrator.
3. **Fixtures ship to production regardless.** Because the branches are inline
   in page components, the demo data is a static import of those pages. A
   production build contains roughly 45 KB of fabricated Persian records —
   `registryDemoData-*.js` (42.5 KB), `maintenanceDemoData-*.js` (2.5 KB), plus
   demo strings inlined into the procurement chunk.
4. **Nothing on screen says the data is fake.** A demo build and a real one look
   identical.

## What is enforced now

### The production refusal

`src/app/configuration/runtimeConfig.ts` ignores `VITE_DEMO_MODE` when
`import.meta.env.PROD` is true, unless `VITE_ALLOW_DEMO_IN_PRODUCTION=true` is
*also* set. Refusing is loud, not silent: the module exports
`demoModeRefusedInProduction` and writes an error to the console, because
somebody who asked for fixtures and is getting real data needs to know.

Two flags rather than one is the point. The second has no other purpose, cannot
be set by accident, and reads as an explicit decision in a deployment config.

Pinned by `src/tests/demoModeProductionGuard.test.ts` (6 specs).

### The banner

`src/shared/components/DemoModeBanner.tsx` renders in the app shell's top bar
whenever demo mode is active. Below 900px it collapses to its dot so it never
pushes the layout around. A demo build is now unmistakable at a glance.

### The ratchet

`src/tests/demoModeBoundary.test.ts` freezes the per-file count of `demoMode`
references and fails the suite when:

- a file that had no demo branches gains one,
- a file that had some gains more,
- a file loses some and the recorded baseline was not lowered to match.

The third case is deliberate. It fails on *improvement*, forcing the baseline
down so the number can only shrink. The branch count is now a number that is
checked rather than a number nobody was watching.

(The ratchet immediately earned its keep: it caught a wrong entry in its own
baseline on first run.)

### The build-time firewall

`vite/demoFixtureFirewall.ts` replaces every fixture module with a stub of the
same export names and no content, unless the build is allowed to contain
fixtures. A runtime flag could never fix point 3 above, because by the time
any flag is read the data is already linked into the bundle.

Stubs preserve shape — an array export becomes `[]`, an object `{}` — so a
code path that still reaches for fixtures renders empty rather than crashing.
Demo *service factories* are the exception: they throw, because reaching one
in a non-demo build is a routing bug and a loud failure in staging beats a
blank page in front of a customer.

Fabricated records that used to sit inline inside page components
(`ProcurementPage`'s supplier, `AccountPage`'s administrator,
`AdministrationPage`'s role, `SparePartsPage`'s warehouse) were invisible to
any module-level rule. They now live in `src/features/demo/pageDemoFixtures.ts`,
which the firewall covers.

Measured on a `VITE_DEMO_MODE=false` build: **zero** fabricated records in 66
build artefacts, down from 45 KB. With
`VITE_ALLOW_DEMO_IN_PRODUCTION=true` they come back, which is the point.

### Error states instead of fabrications

`src/shared/components/ErrorState.tsx` is what a page shows when the request
failed. It replaces two bad habits: `.catch(() => setRows([]))`, which made a
failed request indistinguishable from an empty warehouse, and the demo
fallback, which replaced the failure with fiction. It is on screen rather than
in a toast, and it carries the retry.

Wired into `SparePartsPage`, `ProcurementPage` and `AdministrationPage`
(users and roles) — the pages where a swallowed failure was most misleading.

### The isolation test

`src/tests/demoFixtureIsolation.test.tsx` renders **20 pages** with
`demoMode: false` and `fetch` rejecting every request, then asserts that none
of the fixtures' signature strings reached the DOM. This is the test that
catches the case the other two miss: a page that is handed real conditions and
reaches for fake data anyway.

It was verified by mutation — reintroducing `useState(demoParts)` in
`MaintenanceDashboardPage` made it fail with `تسمه V118, سیل مکانیکی 45mm`.

`npm run verify:demo-boundary` builds with demo mode off and greps the
artefacts, so the claim is checked against what actually ships and not only
against the rules that are supposed to produce it.

## What is still outstanding

The fixtures are gone from production builds and no page consumes them with
demo mode off. What remains is structural: the branches are frozen, not
removed. The real fix is the seam this project
already has and does not use consistently:

```ts
// src/features/registry/registryService.ts — the pattern that is right
const service = runtimeConfig.demoMode
  ? createDemoRegistryService()
  : createRegistryService(api);
```

Chosen once, at the top, in `AssetHierarchyPage.tsx:134`. Everything below that
line is written against one interface and contains no `demoMode` reference at
all. Every other page instead asks "am I in demo mode?" over and over, inline,
in render bodies.

### The plan, heaviest first

| File | Branches |
| --- | --- |
| `pages/WorkOrdersPage.tsx` | 27 |
| `pages/ProcurementPage.tsx` | 16 |
| `pages/SparePartsPage.tsx` | 10 |
| `pages/MaintenanceDashboardPage.tsx` | 9 |
| `pages/DashboardPage.tsx` | 7 |
| `pages/MaintenanceDevicesPage.tsx` | 7 |
| 29 further files | ≤ 5 each |

For each: define the service interface the page actually needs, write the live
and demo implementations behind it, select once, delete the inline branches,
lower the ratchet baseline. One page per change, with the existing suite as the
regression net.

When a page's demo data reaches a service module that is only imported by the
demo implementation, that fixture also becomes dynamically importable and stops
shipping in the production bundle. Removing the 45 KB is a consequence of the
refactor, not a separate task.

### Not covered by any of this

`demoLogin` still accepts any password **in a development build**. That is what
demo mode is for and is fine. What is no longer fine is reaching it from a
production build by accident.
