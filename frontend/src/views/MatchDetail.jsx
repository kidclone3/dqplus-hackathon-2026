import { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { riseIn, prefersReduced } from '../lib/anim.js';
import './matches.css';

const clamp = (n) => Math.max(0, Math.min(100, Math.round(n)));

export default function MatchDetail({ candidate, rank, intent, emailLang, onLang, copied, onCopy, draftText, onBack }) {
  const rootRef = useRef(null);
  const scoreRef = useRef(null);

  useGSAP(() => {
    if (!rootRef.current) return;
    riseIn(rootRef.current);
    if (prefersReduced()) return;
    if (scoreRef.current) {
      gsap.from(scoreRef.current, { textContent: 0, duration: 0.8, ease: 'power2.out', snap: { textContent: 1 } });
    }
    const bars = rootRef.current.querySelectorAll('.vn-detail-bar-fill');
    if (bars.length) {
      gsap.from(bars, { scaleX: 0, transformOrigin: 'left center', duration: 0.7, ease: 'power3.out', stagger: 0.08 });
    }
  }, { scope: rootRef, dependencies: [candidate] });

  const breakdown = [
    { label: 'Profile similarity', val: clamp(candidate.vectorScore) },
    { label: 'Attribute fit', val: clamp(candidate.attributeScore) },
  ];
  const facts = [
    (intent === 'talent' ? 'Role · ' : 'Type · ') + candidate.type,
    ...(candidate.sectors.length ? ['Focus · ' + candidate.sectors.join(', ')] : []),
    'Fit score · ' + candidate.score + '/100',
  ];

  return (
    <div className="vn-detail-root" ref={rootRef}>
      <a className="link rise" onClick={onBack}>← All matches</a>

      <div className="vn-detail-header rise">
        <div>
          <div className="vn-detail-type">
            <span className="dot" style={{ background: candidate.dot }}></span>
            {candidate.type}
          </div>
          <h1 className="serif-h1 vn-detail-name">{candidate.name}</h1>
          <div className="vn-detail-sectors">
            {candidate.sectors.map((sec) => (
              <span className="chip vn-detail-sector-chip" key={sec}>{sec}</span>
            ))}
          </div>
        </div>
        <div className="vn-detail-score-wrap">
          <div className="vn-detail-score"><span ref={scoreRef}>{candidate.score}</span></div>
          <div className="vn-detail-score-caption">Fit score</div>
        </div>
      </div>

      <section className="card rise vn-detail-section">
        <div className="card-label accent">Why this match</div>
        <p className="vn-detail-rationale">{candidate.rationale}</p>
      </section>

      <section className="card rise vn-detail-section">
        <div className="vn-detail-breakdown-head">
          <div className="card-label">Fit breakdown</div>
          <div className="vn-detail-breakdown-meta">rank #{rank}</div>
        </div>
        {breakdown.map((b) => (
          <div className="vn-detail-bar-row" key={b.label}>
            <span className="vn-detail-bar-label">{b.label}</span>
            <span className="vn-detail-bar-track">
              <i className="vn-detail-bar-fill" style={{ width: b.val + '%' }}></i>
            </span>
            <b className="vn-detail-bar-val">{b.val}</b>
          </div>
        ))}
      </section>

      {candidate.reasons.length > 0 && (
        <section className="vn-detail-flat rise vn-detail-section">
          <div className="card-label vn-detail-facts-label">Match signals</div>
          <div className="vn-detail-facts">
            {candidate.reasons.map((r) => (
              <div className="vn-detail-fact" key={r}>{r}</div>
            ))}
          </div>
        </section>
      )}

      <section className="vn-detail-flat rise vn-detail-section">
        <div className="card-label vn-detail-facts-label">Key facts</div>
        <div className="vn-detail-facts">
          {facts.map((f) => (
            <div className="vn-detail-fact" key={f}>{f}</div>
          ))}
        </div>
      </section>

      <section className="card rise vn-detail-section">
        <div className="vn-detail-draft-head">
          <div className="card-label">Draft introduction</div>
          {draftText && (
            <div className="seg vn-detail-lang-seg">
              <button type="button" className={'seg-btn' + (emailLang === 'vi' ? ' active' : '')} onClick={() => onLang('vi')}>Tiếng Việt</button>
              <button type="button" className={'seg-btn' + (emailLang === 'en' ? ' active' : '')} onClick={() => onLang('en')}>English</button>
            </div>
          )}
        </div>
        {draftText && (
          <>
            <div className="vn-detail-draft-box">{draftText}</div>
            <div className="vn-detail-copy-row">
              <button type="button" className="btn btn-ghost vn-detail-copy-btn" onClick={onCopy}>{copied ? 'Copied' : 'Copy draft'}</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
