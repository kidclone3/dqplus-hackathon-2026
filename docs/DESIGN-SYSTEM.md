# VietNexus Design System

Single source of truth for the visual language. The tokens live in
`frontend/src/styles.css` (`:root`); landing-page extensions live in
`frontend/src/views/landing.css` (scoped under `.vn-landing`). Reuse these —
never introduce a parallel system.

## 1. Brand

| Element | Value |
|---|---|
| Product | VietNexus · Innovation OS for Vietnam |
| Logo | `frontend/public/logo.png`, always on a 8–9px-radius rounded square |
| Voice | Plain, confident, explainable. No hype verbs ("elevate", "unleash"), no em-dashes (`—`) anywhere in visible copy — use a period, comma, or colon instead |
| Theme | Light, locked. The dark closing panel (`#12241d`) is the one deliberate color-block per page |

## 2. Typography

| Role | Font | Usage |
|---|---|---|
| UI / body | **Hanken Grotesk** (`--font-ui`) | Nav, body copy, buttons, labels, data |
| Display / editorial | **Newsreader** (`--font-serif`) | H1/H2 headlines, big numbers (scores), pull-quotes |

Loaded via Google Fonts in `frontend/index.html` (weights: Hanken 400–800, Newsreader 400–500 optical).

- Display headlines: serif, weight 400, `letter-spacing: -0.02em`, line-height 1.08–1.16.
- Emphasis inside a headline: *italic of the same serif*, colored `--accent`. Never mix a second family in.
- Italic words with descenders (y g j p q) need `line-height ≥ 1.1` + bottom padding reserve so nothing clips.
- Body: 14–19px, line-height 1.5–1.62, max-width ~65ch.
- Eyebrows: 12px, uppercase, `letter-spacing 0.14em`, weight 600, color `--accent`. **Ration: max 1 eyebrow per 3 sections.**

## 3. Color tokens (`:root` in styles.css)

### Surfaces
| Token | Value | Use |
|---|---|---|
| `--bg` | `#f6f5f1` | Page background (warm paper) |
| `--card` | `#fff` | Cards, elevated panels |
| `--input-bg` | `#fbfaf7` | Inputs, inset panels ("Why now" box) |
| `--chip-off` | `#efece4` | Inactive chips |

### Borders
| Token | Value | Use |
|---|---|---|
| `--border` | `#e7e5dd` | Card borders |
| `--border-soft` | `#eceae2` | Inner dividers |
| `--hairline` | `#f0efe8` | Faintest rules |
| `--input-border` | `#ddd9cf` | Inputs, ghost buttons |
| `--lp-line` (landing only) | `#e4e1d7` | Editorial hairline grids/dividers |

### Ink scale (dark → light)
`--ink #1a1a17` · `--heading #1f1f19` · `--label #3a3a33` · `--body #4a4a42` · `--text #5f5e55` · `--dim #6b6b62` · `--muted #8a887f` · `--faint #a3a196`

### Accent (the only accent — Color Consistency Lock)
| Token | Value |
|---|---|
| `--accent` | `#1f7a5c` (brand green) |
| `--accent-soft` | `rgba(31,122,92,.10)` |
| `--accent-softer` | `rgba(31,122,92,.06)` |
| `--accent-badge` | `rgba(31,122,92,.12)` |
| Dark panel | `#12241d` + radial glow `rgba(31,122,92,.4)` |

### Error family
`--err #c0503f` with bg/border/input variants (see styles.css). Errors only — never decoration.

### Actor dots (landing, semantic category colors)
startup `#3f8f6b` · vc `#b08636` · corp `#3f6c9c` · uni `#7a5aa6` · research `#3f8f8f` · gov `#a65a6b`

Desaturated by design; do not brighten. Max 1 accent elsewhere.

## 4. Shape (radius scale)

| Element | Radius |
|---|---|
| Buttons (all, app + landing), chips, pills, badges | full pill (`999px`) |
| Inputs / selects | 11px |
| Small tiles (avatars, "Why now" box, score tile) | 12–16px |
| Cards | 18–20px |
| Hero-level panels (dark CTA box) | 26px |

Rule: interactive = pill everywhere; inputs 11px; containers = 18–26px growing with size. Don't mix outside this table.

## 5. Elevation & shadow

- Shadows are **tinted to the surface hue**, never pure black: `rgba(24,40,32,…)` on paper, `rgba(18,52,40,…)` under green buttons.
- App cards: `--shadow-card` (near-flat). Landing showcase cards: `0 30px 70px -30px rgba(24,40,32,.28)`.
- Prefer hairline borders + whitespace over cards. A card must earn its elevation; grouped content uses `border-top` dividers (see `.vn-guarantee`, `.vn-actors`).

## 6. Buttons

### Base (`styles.css`, app-wide)
- All buttons are **full pills**.
- `.btn-primary` — depth gradient `#228566 → #1a6a4f`, 1px inner top highlight, green-tinted shadow (`rgba(18,52,40,.5)`). Hover: brighter gradient + deeper shadow.
- `.btn-ghost` — transparent, `--input-border` hairline border, `--ink` text.
- `:focus-visible`: 2px `--accent` outline, 2px offset. Always.
- `:active`: 1px press-down. Tactile.
- Disabled: `opacity .6`, `cursor: not-allowed`, no transform.

### Landing additions (`landing.css`, scoped `.vn-landing`)
- `.btn-lg`: 54px tall, 0 30px padding, 15px text; hover 1px lift + arrow slides 3px.
- Ghost hover: firmer border + translucent white fill.
- **`.btn-on-dark`**: warm off-white gradient `#fdfcfa → #efede7`, inner highlight, deep shadow. For the dark panel only.

### Muted-primary state (forms)
When a primary CTA is present but not yet actionable (e.g. "Mark as Ready" with an incomplete form), do not fade the green button (contrast failure). Use the muted variant: `--card` fill, `--label` text, `--input-border` border, no shadow (see `.vn-form-cta-muted`).

### CTA copy rules
- **One label per intent.** App entry = "Open the app" everywhere (nav, hero, dark panel). Never introduce synonyms ("Start your journey", "Get started").
- Labels ≤ 4 words, never wrap at desktop.

## 7. Chips, dots, metadata

- Chips: pill, 12–13px, weight 500–600. Active = `--accent-soft` bg + `--accent` text.
- Dots (7–9px circles) carry **semantic category color only** (the six actors, app status). Zero decorative dots.
- Middle-dot `·` separator: **max 1 per metadata line** ("Healthtech seed · Hanoi, 2024").
- Fake-precise numbers are labelled: showcase cards say "Sample data".

## 8. Layout

- Content container: `max-width 1200px`, gutter `clamp(20px, 5vw, 64px)`.
- Section rhythm: `padding clamp(64px, 9vw, 128px)` vertical (airy = premium; VISUAL_DENSITY ~3).
- Nav: 68px, sticky, `backdrop-filter: blur(14px)` over translucent paper; hairline bottom border appears only after scroll (`.is-stuck`).
- Landing layout families in use (one appearance each): asymmetric split hero (1.06fr/0.94fr) · editorial head + hairline cell grid · stacked head + split body with divider list · centered dark color-block. Don't repeat a family on one page.
- Breakpoints: 940px (grids → 1 col), 600px (nav links hide, actor grid → 1 col).
- Never `h-screen`/`100vh` heroes; hero height is content-driven.

## 9. Motion (GSAP)

Helpers in `frontend/src/lib/anim.js`. MOTION_INTENSITY ~5: fluid, restrained.

| Pattern | Spec |
|---|---|
| Load rise (`riseIn`, `.rise`) | `y:18 → 0`, autoAlpha, 0.5s `power2.out`, stagger 0.06 |
| Scroll reveal (`.vn-reveal`) | `y:26 → 0`, autoAlpha, 0.7s, ScrollTrigger `top 82%`, once |
| Score count-up (`[data-count]`) | 0 → value, 1.1s, fires at `top 88%` (draws the eye to the fit number) |
| Hover physics | CSS only: 1px lift, arrow slide, `cubic-bezier(0.16,1,0.3,1)` |

Rules:
- Every animation must justify itself (hierarchy, feedback, storytelling). No motion for motion's sake.
- **`prefers-reduced-motion` is honored everywhere** — `prefersReduced()` guards all GSAP; CSS transitions zeroed in the media query.
- Animate `transform`/`opacity` only. No `window.addEventListener('scroll')` — ScrollTrigger or IntersectionObserver.

## 10. Anti-patterns (banned)

- Em-dashes (`—`, and `–` as separator) in any visible string.
- Section-number eyebrows (`01 / Reasoning`), version labels, scroll cues ("scroll to explore").
- Decorative status dots, > 1 middle-dot per line, pills overlaid on images.
- Fake filled progress-bar tracks as decoration; unlabelled fake-precise numbers.
- Three-equal-card feature rows; the same layout family twice on a page.
- More than 1 eyebrow per 3 sections.
- A second accent color, pure `#000`, purple/neon gradients, outer glows.
- Duplicate CTA intents with different labels.
- New global CSS without a view namespace (landing uses `vn-*` under `.vn-landing`).
