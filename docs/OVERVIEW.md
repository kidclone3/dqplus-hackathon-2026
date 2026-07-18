# VietNexus — Overview

> **A smart matchmaker for Vietnam's startup world.** VietNexus helps startups find the
> right investors — and helps that startup's story reach the right partners around the
> world.
>
> Hackathon project · `dqplus-hackathon-2026` · VAIC 2026, challenge #135
> (Deal-flow Matchmaker, sponsored by NIC) · July 2026.

*This overview is written for everyone. For the technical details, see
[`ARCHITECTURE.md`](ARCHITECTURE.md) and [`TECHNOLOGY.md`](TECHNOLOGY.md).*

---

## 1. The problem

Vietnam has a fast-growing community of startups, but connecting the right people is still
slow, manual, and mostly depends on who you happen to know:

- **Founders** struggle to find investors who are actually a good fit — the right industry,
  the right stage, the right amount of money. So they reach out to everyone and get
  ignored by most.
- **Investors** get flooded with pitches that don't match what they're looking for, and
  miss great companies simply because those companies aren't in their circle.
- **The language gap** — a promising Vietnamese startup usually doesn't have a clear,
  convincing pitch in English, so international investors and partners never hear its story.

The result: good companies don't get funded, and good money doesn't reach them.

## 2. What VietNexus does

Think of VietNexus as an expert matchmaker that never sleeps. You tell it about yourself,
and it hands you a short, ranked list of the people most worth talking to — and explains
*why* each one is a good fit.

Here's the journey:

1. **Sign up and introduce yourself.** A founder or investor fills in a short profile:
   what the company does, what stage it's at, its industry, where it operates, and (for
   investors) how much they typically invest.
2. **VietNexus understands you.** Behind the scenes, an AI reads your profile and turns it
   into a clear, structured summary of who you are and what you're looking for.
3. **It finds your best matches.** VietNexus compares you against everyone on the other
   side of the market and ranks them by how well they fit — combining the *meaning* of what
   you do with concrete facts like industry, stage, and investment size.
4. **You see the reasons.** Every match comes with a plain-language explanation ("same
   industry: fintech · matches your stage: seed · invests in your region"), so you can
   trust the list instead of guessing.
5. **You reach out.** With one click you get a ready-to-send introduction message to start
   the conversation.

For deeper research, a companion system (the **AI Data Platform**) goes further: it looks
up real information about each company from the web, keeps a link to every source so nothing
is made up, and has a second AI double-check every message to remove anything that isn't
true. In short — **the right match, with the proof to back it up.**

## 3. Who it's for

| User | What they get |
|------|---------------|
| **Founders** | A short list of investors who genuinely fit their fundraising, each with a clear reason and a ready-to-send intro. |
| **Investors** | A relevant pipeline of startups worth their time, instead of endless cold pitches. |
| **Ecosystem builders** (like NIC and accelerators) | A trustworthy, transparent way to connect the whole innovation community. |

## 4. Four kinds of connections — and honest about what's ready

The app is built around four things a founder might be looking for. Only the first is fully
working today; the others are shown with an honest "coming soon" note instead of pretending
with fake results.

| You're looking for… | Status |
|---------------------|--------|
| **Investors** that fit your raise | ✅ Working today |
| Potential customers | 🔜 Coming soon |
| Partners & mentors for R&D | 🔜 Coming soon |
| Talent to join your team | 🔜 Coming soon |

## 5. What's inside

VietNexus has two parts that work together:

- **The app** — the website and mobile app that founders and investors actually use, plus
  the services behind them that handle sign-in, profiles, and matching.
- **The AI Data Platform** — a more powerful research engine that gathers real evidence
  from the web and fact-checks every introduction. (Its own overview is in
  [`ai-data-platform/docs/OVERVIEW.md`](../ai-data-platform/docs/OVERVIEW.md).)

## 6. What works today, and what's next

**Working end to end right now:**

- Sign up, sign in, and fill in your profile (on both web and mobile).
- The AI reads your profile and prepares it for matching. It works with a paid AI service
  for the best results, and also has a built-in backup so it keeps working even without
  one.
- Matching that ranks the other side of the market and explains its reasons.
- A live public website at **https://dqplus.ddns.net**.

**Still in progress:**

- The customers, partners, and talent connections don't have a working engine yet (the app
  says so honestly).
- The introduction messages in the app are built from a simple template today; the
  fully-researched, fact-checked version lives in the AI Data Platform and isn't wired into
  the app yet.

## 7. Learn more

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how the pieces fit together (technical).
- [`TECHNOLOGY.md`](TECHNOLOGY.md) — the tools we used and why (technical).
- [`ai-data-platform/docs/`](../ai-data-platform/docs/) — the research engine's own docs.
