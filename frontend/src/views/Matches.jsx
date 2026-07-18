import { useRef, useState, useEffect } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { INTENTS } from '../data/ecosystem.js';
import { prefersReduced } from '../lib/anim.js';
import { entityMeta } from '../lib/api.js';
import './matches.css';

const SKELETON_ROWS = [0, 1, 2];

// Multi-select checkbox popover (shadcn-style pattern, styled with our tokens).
function SectorSelect({ options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = (s) =>
    onChange(selected.includes(s) ? selected.filter((x) => x !== s) : [...selected, s]);
  const label =
    selected.length === 0 ? 'All sectors' : selected.length === 1 ? selected[0] : selected.length + ' sectors';

  return (
    <div className="vn-sector-select" ref={wrapRef}>
      <button
        type="button"
        className={'vn-match-filter-chip vn-sector-trigger' + (selected.length ? ' active' : '')}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {label}
        <span className="vn-sector-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="vn-sector-menu">
          {options.map((s) => (
            <label className="vn-sector-item" key={s}>
              <input type="checkbox" checked={selected.includes(s)} onChange={() => toggle(s)} />
              <span>{s}</span>
            </label>
          ))}
          {selected.length > 0 && (
            <button type="button" className="vn-sector-clear" onClick={() => onChange([])}>
              Clear selection
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function Matches({ role, profileName, intent, live, matchStatus, matchError, onRetry, onIntent, topK, onTopK, filter, onFilter, typeOptions, sectorOptions, items, total, title, sub, onOpen, onBackToForm }) {
  const rootRef = useRef(null);

  useGSAP(() => {
    if (prefersReduced() || !rootRef.current) return;
    const cards = rootRef.current.querySelectorAll('.vn-match-card');
    if (!cards.length) return;
    gsap.from(cards, { y: 14, autoAlpha: 0, duration: 0.45, ease: 'power2.out', stagger: 0.05, clearProps: 'all' });
  }, { scope: rootRef, dependencies: [intent, topK, matchStatus, filter] });

  const ready = live && matchStatus === 'ready';
  const filtering = filter.type !== 'all' || filter.sectors.length > 0;
  const clearFilters = () => onFilter({ type: 'all', sectors: [] });

  const openCard = (candidate, rank) => onOpen({ candidate, rank });

  return (
    <div className="vn-match-root" ref={rootRef}>
      <a className="link" onClick={onBackToForm}>← Edit profile</a>
      <div className="eyebrow vn-match-eyebrow">Matches · reasoning-ranked</div>
      <h1 className="serif-h1 vn-match-h1">{title}</h1>
      <p className="lede vn-match-lede">{sub} Scored 0 to 100 so you don't spend time searching.</p>

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

      {ready && (typeOptions.length > 1 || sectorOptions.length > 1) && (
        <div className="vn-match-filters">
          {typeOptions.length > 1 && (
            <div className="vn-match-filter-group">
              <span className="vn-match-filter-label">Type</span>
              {['all', ...typeOptions].map((t) => (
                <button
                  key={t}
                  type="button"
                  className={'vn-match-filter-chip' + (filter.type === t ? ' active' : '')}
                  onClick={() => onFilter({ ...filter, type: t })}
                >
                  {t !== 'all' && <span className="dot" style={{ background: entityMeta(t).dot }}></span>}
                  {t === 'all' ? 'All' : entityMeta(t).label}
                </button>
              ))}
            </div>
          )}
          {sectorOptions.length > 1 && (
            <div className="vn-match-filter-group">
              <span className="vn-match-filter-label">Sector</span>
              <SectorSelect
                options={sectorOptions}
                selected={filter.sectors}
                onChange={(sectors) => onFilter({ ...filter, sectors })}
              />
            </div>
          )}
        </div>
      )}

      {ready && items.length > 0 && (
        <div className="vn-match-count-row">
          <span className="vn-match-count">Showing top {items.length} of {total}</span>
          <div className="seg vn-match-seg">
            <button type="button" className={'seg-btn' + (topK === 5 ? ' active' : '')} onClick={() => onTopK(5)}>Top 5</button>
            <button type="button" className={'seg-btn' + (topK === 10 ? ' active' : '')} onClick={() => onTopK(10)}>Top 10</button>
            <button type="button" className={'seg-btn' + (topK >= total ? ' active' : '')} onClick={() => onTopK(999)}>All</button>
          </div>
        </div>
      )}

      {!live && (
        <div className="vn-match-state">
          <p className="vn-match-state-text">This match type isn't connected to a backend service yet. Only {role === 'investor' ? 'startup' : 'investor'} matching is live today.</p>
        </div>
      )}

      {live && matchStatus === 'loading' && (
        <div className="vn-match-loading" aria-busy="true" aria-live="polite">
          <span className="vn-match-loading-label">Ranking matches from your profile…</span>
          <div className="vn-match-skeleton" aria-hidden="true">
            {SKELETON_ROWS.map((i) => (
              <div className="vn-match-skel-card" key={i}>
                <span className="vn-skel vn-skel-rank" />
                <span className="vn-skel vn-skel-score" />
                <div className="vn-match-skel-body">
                  <span className="vn-skel vn-skel-line vn-skel-type" />
                  <span className="vn-skel vn-skel-line vn-skel-name" />
                  <span className="vn-skel vn-skel-line vn-skel-rationale" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {live && matchStatus === 'error' && (
        <div className="vn-match-state vn-match-state-error">
          <p className="vn-match-state-title">Couldn't rank your matches</p>
          <p className="vn-match-state-text">{matchError}</p>
          <button type="button" className="btn btn-ghost" onClick={onRetry}>Try again</button>
        </div>
      )}

      {ready && items.length === 0 && (
        <div className="vn-match-state">
          {filtering ? (
            <>
              <p className="vn-match-state-text">No matches under these filters.</p>
              <button type="button" className="btn btn-ghost" onClick={clearFilters}>Clear filters</button>
            </>
          ) : (
            <p className="vn-match-state-text">No matches yet. As more {role === 'investor' ? 'startups' : 'investors'} join the ecosystem, they'll show up here ranked by fit.</p>
          )}
        </div>
      )}

      {ready && (
        <div className="vn-match-list">
          {items.map(({ candidate, rank }) => (
            <article
              key={candidate.userId}
              className="vn-match-card rise"
              role="button"
              tabIndex={0}
              onClick={() => openCard(candidate, rank)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  openCard(candidate, rank);
                }
              }}
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
              </div>
              <span className="vn-match-analysis">Analysis <span className="vn-match-analysis-arrow">→</span></span>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
