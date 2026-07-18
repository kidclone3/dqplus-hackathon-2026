# Frontend Roadmap — web (`frontend/`) + mobile (`mobile/`)

Component roadmap under the [system roadmap](../ROADMAP.md). Current stack: Vite +
React 18 + GSAP (web), Expo / React Native (mobile). Design language is defined in
[`../DESIGN-SYSTEM.md`](../DESIGN-SYSTEM.md) — everything below reuses those tokens.

## Today

- **Web is live and mock-free**: auth gate, onboarding profile form, matches list +
  match detail, admin-gated platform dashboard link. Matches come from the real
  `/api/matches` chain with the 404 → auto-extract → retry flow in `App.jsx` / `lib/api.js`.
- **Honest limits shown in-product**: customers / partners / talent tabs display a
  "not connected" notice; outreach drafts are generated client-side (`lib/draft.js`);
  consent + draft-ready flags live only in `localStorage` (`vn.profile.<username>`).
- **Mobile mirrors the web screens but runs entirely on `src/data/mockData.js`.**

## Phase 1 — Demo-hard

| Item | Definition of done |
|------|--------------------|
| Real outreach drafts | Match detail requests the platform's bilingual fact-checked draft; template kept as an offline/loading fallback; vi/en toggle on the draft card |
| Server-persisted consent & draft state | Flags round-trip through gateway `profiles`; `localStorage` becomes a cache, not the source of truth |
| Error surfaces | Every API failure has a designed state (retry, "extraction running", backend-down) — no silent spinners |
| Smoke tests in CI | Playwright run of register → profile → matches against the compose stack |

## Phase 2 — Product

| Item | Definition of done |
|------|--------------------|
| Light up the intent tabs | As each partner-type backend route ships, the corresponding tab renders real matches; the "not connected" notice is deleted per-tab, not globally |
| Mobile on real APIs | Expo app talks to the same `/api/*` contract (shared client module with web where practical); `mockData.js` deleted |
| Session hygiene | Refresh-token support in the client, graceful re-auth instead of dumping the user to the gate |
| Match feedback UI | Accept / pass / contacted actions on each match card, POSTed to the backend (feeds ranking later) |

## Phase 3 — Scale & ecosystem

- **Full vi/en localization** of both clients (strings externalized; drafts already bilingual).
- **Graph view for end users** — a simplified, user-facing cut of the dashboard's
  GraphRAG explorer showing *why* a match connects to you (shared network, sector paths).
- **Cohort/program skin**: accelerator-branded instances reusing the same component set.
- **Performance budget**: keep the landing + app bundle within a stated budget; GSAP
  animation honors `prefers-reduced-motion` throughout.

## Standing constraints

- CSS is global — keep namespacing view-specific classes (`vn-lp-*` pattern).
- Reuse `styles.css` tokens (`--accent`, `--font-ui`/`--font-serif`, `.btn*`); never
  introduce a parallel design system.
- Web deploys go through `deploy/rolling-deploy.sh` only (zero-downtime constraint).
