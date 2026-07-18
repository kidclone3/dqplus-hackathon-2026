import { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { INTENTS } from '../data/ecosystem.js';
import { prefersReduced } from '../lib/anim.js';
import './matches.css';

export default function Matches({ role, profileName, intent, onIntent, topK, onTopK, items, total, title, sub, onOpen, onBackToForm }) {
  const rootRef = useRef(null);

  useGSAP(() => {
    if (prefersReduced() || !rootRef.current) return;
    const cards = rootRef.current.querySelectorAll('.vn-match-card');
    if (!cards.length) return;
    gsap.from(cards, { y: 14, autoAlpha: 0, duration: 0.45, ease: 'power2.out', stagger: 0.05, clearProps: 'all' });
  }, { scope: rootRef, dependencies: [intent, topK] });

  return (
    <div className="vn-match-root" ref={rootRef}>
      <a className="link" onClick={onBackToForm}>← Edit profile</a>
      <div className="eyebrow vn-match-eyebrow">Matches · reasoning-ranked</div>
      <h1 className="serif-h1 vn-match-h1">{title}</h1>
      <p className="lede vn-match-lede">{sub} Scored 0–100 so you don't spend time searching.</p>

      <div className="vn-match-tabs">
        {INTENTS.map((it) => (
          <button
            key={it.id}
            type="button"
            className={'vn-match-tab' + (it.id === intent ? ' active' : '')}
            onClick={() => onIntent(it.id)}
          >
            {it.id === 'investors' && role === 'investor' ? 'Startup' : it.tab}
          </button>
        ))}
      </div>

      <div className="vn-match-count-row">
        <span className="vn-match-count">Showing top {items.length} of {total}</span>
        <div className="seg vn-match-seg">
          <button type="button" className={'seg-btn' + (topK === 5 ? ' active' : '')} onClick={() => onTopK(5)}>Top 5</button>
          <button type="button" className={'seg-btn' + (topK === 10 ? ' active' : '')} onClick={() => onTopK(10)}>Top 10</button>
          <button type="button" className={'seg-btn' + (topK >= total ? ' active' : '')} onClick={() => onTopK(999)}>All</button>
        </div>
      </div>

      <div className="vn-match-list">
        {items.map(({ candidate, rank }) => (
          <article
            key={candidate.name}
            className="vn-match-card rise"
            onClick={() => onOpen({ candidate, rank })}
          >
            <div className="vn-match-rank">#{rank}</div>
            <div className="vn-match-score">{candidate.score}</div>
            <div className="vn-match-body">
              <div className="vn-match-type">
                <span className="dot" style={{ background: candidate.dot }}></span>
                {candidate.type}
              </div>
              <h3 className="vn-match-name">{candidate.name}</h3>
              <p className="vn-match-rationale">{candidate.rationale}</p>
              {candidate.people && candidate.people.length > 0 && (
                <div className="vn-match-people">
                  {candidate.people.map((p) => (
                    <div className="vn-match-person" key={p.name}>
                      <span className="vn-match-arrow">→</span>
                      <b>{p.name}</b>
                      <span className="vn-match-sep">·</span>
                      <span className="vn-match-role">{p.role}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <span className="vn-match-analysis">Analysis →</span>
          </article>
        ))}
      </div>
    </div>
  );
}
