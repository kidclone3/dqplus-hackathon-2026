# VietNexus Web

Frontend for VietNexus — Innovation OS (Vite + React 18 + GSAP), built from the
"VietNexus Onboarding" prototype.

Flow: auth gate → single profile form (Startup/Investor, Draft/Ready) →
reasoning-ranked matches (Investment Fund / Potential customers / Partners & mentors / Talent)
→ match analysis with fit breakdown and bilingual (VI/EN) draft introductions.

## Run

```bash
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api/*` to the backend gateway (`backend/gateway`,
default `http://localhost:3000`; override with `GATEWAY_URL`). Auth and profile
data persist through the gateway (`/auth/register`, `/auth/login`, `/profiles`).
If the gateway is unreachable, the auth screen offers a local demo mode.

Match datasets are currently static (`src/data/ecosystem.js`) — the matching
engine is not built yet.

## Structure

- `src/App.jsx` — session, profile form state, view routing (form/matches/detail)
- `src/views/` — AuthGate, ProfileForm, Matches, MatchDetail (+ per-view CSS)
- `src/components/Header.jsx` — sticky header with Draft/Ready status
- `src/lib/api.js` — gateway client + profile field mapping
- `src/lib/draft.js` — bilingual intro draft generator
- `src/lib/anim.js` — GSAP entrance helpers (respects `prefers-reduced-motion`)
- `src/styles.css` — design tokens + shared components
