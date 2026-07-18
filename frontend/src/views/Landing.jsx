import { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import { riseIn } from '../lib/anim.js';
import './landing.css';

const ACTORS = [
  { dot: 'var(--dot-startup)', title: 'Startups', desc: 'Ideas seeking momentum' },
  { dot: 'var(--dot-vc)', title: 'Venture Capital', desc: 'Capital with a thesis' },
  { dot: 'var(--dot-corp)', title: 'Corporations', desc: 'Scale and distribution' },
  { dot: 'var(--dot-uni)', title: 'Universities', desc: 'Talent and licensable IP' },
  { dot: 'var(--dot-research)', title: 'Research', desc: 'Deep expertise' },
  { dot: 'var(--dot-gov)', title: 'Government', desc: 'Policy and programs' },
];

const STEPS = [
  {
    n: '01',
    title: 'Its reasoning',
    body: 'Why this match, why now, and why not the others — stated in plain language before you commit attention.',
  },
  {
    n: '02',
    title: 'Its evidence',
    body: "Every claim carries a source, a confidence, and a date. Where we don't know, we say so — never invented.",
  },
  {
    n: '03',
    title: 'The path to outcome',
    body: 'From a scored match to a bilingual introduction to a human-reviewed handshake — the full route, one step at a time.',
  },
];

const BARS = [
  { label: 'Sector fit', pct: 95, score: 95 },
  { label: 'Stage fit', pct: 85, score: 85 },
  { label: 'Geography', pct: 80, score: 80 },
];

export default function Landing({ onEnter }) {
  const rootRef = useRef(null);

  useGSAP(() => {
    if (rootRef.current) riseIn(rootRef.current);
  }, { scope: rootRef });

  return (
    <div className="vn-landing" id="top" ref={rootRef}>
      <header className="vn-landing-header">
        <a href="#top" className="vn-landing-brand">
          <img src="/logo.png" alt="VietNexus" />
          <span className="vn-landing-lockup">
            <b>VietNexus</b>
            <small>INNOVATION OS</small>
          </span>
        </a>
        <nav className="vn-landing-nav">
          <a href="#how">How it works</a>
          <a href="#actors">Ecosystem</a>
          <a href="#match">Explained match</a>
          <button type="button" className="btn btn-primary" onClick={onEnter}>
            Open the app
          </button>
        </nav>
      </header>

      <main>
        {/* HERO */}
        <section className="vn-hero">
          <div className="vn-hero-inner">
            <div>
              <div className="vn-hero-badge rise">
                <span className="dot" />
                An operating system, not a directory
              </div>
              <h1 className="rise">
                AI <span className="accent">Vietnam's</span> innovation ecosystem
              </h1>
              <p className="vn-hero-lede rise">
                VietNexus connects startups with venture capital, corporations, and universities
                through explainable AI matches. Every recommendation opens with its reasoning, its
                evidence, and the path from introduction to outcome.
              </p>
              <div className="vn-hero-cta rise">
                <button type="button" className="btn btn-primary btn-lg btn-hero" onClick={onEnter}>
                  Start your journey <span className="btn-arrow">→</span>
                </button>
                <a href="#match" className="btn btn-ghost btn-lg btn-hero">
                  See a live explained match
                </a>
              </div>
            </div>

            <div className="vn-lp-card rise">
              <div className="card-eyebrow">Explained match</div>
              <div className="vn-lp-org">
                <span className="vn-lp-avatar" style={{ background: '#2f9e78' }}>LV</span>
                <div>
                  <div className="name">Loopwell — healthtech, seed</div>
                  <div className="meta">Founded Hanoi, 2024</div>
                </div>
              </div>
              <div className="vn-lp-evidence">
                <div className="vn-lp-tags">
                  <span className="vn-lp-tag">Stage match</span>
                  <span className="vn-lp-tag">2 prior healthtech deals</span>
                </div>
                <p>
                  Evidence: portfolio overlap with 3 seed healthtech rounds in 2025, avg. check size
                  within founder's target range.
                </p>
              </div>
              <div className="vn-lp-org">
                <span className="vn-lp-avatar" style={{ background: '#c07a34' }}>MC</span>
                <div>
                  <div className="name">Mekong Capital Partners</div>
                  <div className="meta">Seed · Healthtech, SaaS</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ACTORS */}
        <section id="actors" className="vn-landing-wrap">
          <div className="eyebrow-up rise">One ecosystem · six actors</div>
          <h2 className="serif-h2 rise">
            Knowledge flows between the people who build the future together.
          </h2>
          <div className="vn-actor-grid">
            {ACTORS.map((a) => (
              <div className="vn-actor rise" key={a.title}>
                <span className="dot" style={{ background: a.dot }} />
                <div className="title">{a.title}</div>
                <div className="desc">{a.desc}</div>
              </div>
            ))}
          </div>
        </section>

        {/* HOW */}
        <section id="how" className="vn-landing-wrap">
          <div className="eyebrow-up rise">Every recommendation, in the open</div>
          <h2 className="serif-h2 rise">Not a black box. A recommendation you can question.</h2>
          <div className="vn-how-grid">
            {STEPS.map((s) => (
              <div className="vn-how-card rise" key={s.n}>
                <div className="vn-how-num">{s.n}</div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* LIVE EXPLAINED MATCH */}
        <section id="match" className="vn-landing-wrap">
          <div className="vn-live-grid">
            <div>
              <div className="eyebrow-up rise">A live explained match</div>
              <h2 className="serif-h2 rise">
                See exactly why two organisations belong at the same table.
              </h2>
              <p className="vn-live-lede rise">
                A fit score is only the beginning. VietNexus shows the breakdown behind it, the
                sources it stands on, and the introduction it can draft — in Vietnamese or English.
              </p>
              <button type="button" className="btn btn-primary btn-lg rise" onClick={onEnter}>
                Start your journey <span className="btn-arrow">→</span>
              </button>
            </div>

            <div className="vn-lp-card rise">
              <div className="vn-live-head">
                <div>
                  <div className="vn-live-kicker">
                    <span className="dot" style={{ background: 'var(--dot-vc)' }} />
                    Venture Capital
                  </div>
                  <div className="vn-live-title">enfarm × Touchstone Partners</div>
                </div>
                <div className="vn-live-score">89</div>
              </div>
              <div className="vn-bars">
                {BARS.map((b) => (
                  <div className="vn-bar" key={b.label}>
                    <span>{b.label}</span>
                    <span className="vn-bar-track">
                      <i className="vn-bar-fill" style={{ width: `${b.pct}%` }} />
                    </span>
                    <b>{b.score}</b>
                  </div>
                ))}
              </div>
              <div className="vn-why">
                <div className="vn-why-label">Why now</div>
                <p>
                  Capital is actively deploying this quarter, and the Q1 R&amp;D tax-credit window
                  makes co-investment materially cheaper.
                </p>
              </div>
              <div className="vn-live-foot">
                <span>3 public sources · confidence 0.87</span>
                <span className="accent">Draft intro · VI / EN</span>
              </div>
            </div>
          </div>
        </section>

        {/* CLOSING CTA */}
        <section className="vn-closing">
          <div className="vn-closing-box rise">
            <h2>Enter the ecosystem with less uncertainty and more conviction.</h2>
            <p>
              Build a profile once. Get explainable matches, sources, and ready-to-send
              introductions.
            </p>
            <button type="button" className="btn btn-on-dark btn-lg btn-hero" onClick={onEnter}>
              Start your journey <span className="btn-arrow">→</span>
            </button>
          </div>
        </section>
      </main>

      <footer className="vn-landing-footer">
        <div className="vn-landing-footer-inner">
          <div className="vn-landing-footer-brand">
            <img src="/logo.png" alt="VietNexus" />
            <b>VietNexus</b>
          </div>
          <span>Innovation OS</span>
        </div>
      </footer>
    </div>
  );
}
