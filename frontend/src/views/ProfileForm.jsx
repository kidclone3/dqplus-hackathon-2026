import { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import { SECTORS, STAGES } from '../data/ecosystem.js';
import { riseIn } from '../lib/anim.js';
import './form.css';

export default function ProfileForm({
  role,
  form,
  onField,
  onToggleSector,
  status,
  savedAt,
  saving,
  saveError,
  showErrors,
  validity,
  missing,
  onSaveDraft,
  onReady,
}) {
  const rootRef = useRef(null);

  useGSAP(() => {
    if (rootRef.current) riseIn(rootRef.current);
  }, { scope: rootRef, dependencies: [] });

  const isInvestor = role === 'investor';
  const ready = status === 'ready';
  const allValid = missing.length === 0;

  const nameLabel = isInvestor ? 'Fund name' : 'Startup name';
  const namePlaceholder = isInvestor ? 'e.g. Mekong Capital' : 'e.g. enfarm';
  const stageLabel = isInvestor ? 'Stage focus' : 'Stage';
  const needLabel = isInvestor ? 'Collaboration need' : 'Funding need';
  const needPlaceholder = isInvestor
    ? 'What partnerships or deal flow are you looking for?'
    : 'How much are you raising, and what for?';
  const showSummary = showErrors && !allValid;

  let helperText;
  if (ready) {
    helperText = 'Your profile is Ready for matching.';
  } else if (saveError) {
    helperText = saveError;
  } else if (savedAt) {
    helperText = 'Draft saved.';
  } else {
    helperText = 'Draft — not yet visible for matching.';
  }

  const readyLabel = ready ? 'See matches →' : 'Mark as Ready';

  const fieldClass = (base, key) => `${base}${showErrors && !validity[key] ? ' invalid' : ''}`;

  return (
    <div ref={rootRef} className="vn-form-container">
      <div className="eyebrow rise">Your profile · one form</div>
      <h1 className="serif-h1 rise" style={{ marginTop: 12 }}>Tell the ecosystem who you are.</h1>
      <p className="lede rise" style={{ marginTop: 14 }}>
        One calm form. Save a draft anytime — your profile only becomes <b>Ready</b> for matching once the essentials check out.
      </p>

      <div className="rise" style={{ marginTop: 28 }}>
        <span className="chip on" style={{ cursor: 'default' }}>
          {isInvestor ? 'Investor' : 'Startup'} account
        </span>
      </div>

      <div className="vn-form-fields">
        <div className="vn-form-grid rise">
          <div>
            <label className="label">{nameLabel} <span className="req">*</span></label>
            <input
              className={fieldClass('input', 'name')}
              value={form.name}
              onChange={(e) => onField('name', e.target.value)}
              placeholder={namePlaceholder}
            />
            {showErrors && !validity.name && (
              <div className="field-error">This field is required.</div>
            )}
          </div>
          <div>
            <label className="label">
              Website <span className="req">*</span>{' '}
              <span className="vn-form-sector-hint">· comma-separate multiple</span>
            </label>
            <input
              className={fieldClass('input', 'website')}
              value={form.website}
              onChange={(e) => onField('website', e.target.value)}
              placeholder="https://…"
            />
            {showErrors && !validity.website && (
              <div className="field-error">Enter a valid website URL.</div>
            )}
          </div>
        </div>

        <div className="vn-form-grid rise">
          <div>
            <label className="label">{stageLabel} <span className="req">*</span></label>
            <select
              className={fieldClass('select', 'stage')}
              value={form.stage}
              onChange={(e) => onField('stage', e.target.value)}
            >
              <option value="">Select…</option>
              {STAGES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            {showErrors && !validity.stage && (
              <div className="field-error">Please select a stage.</div>
            )}
          </div>
          <div>
            <label className="label">Where you operate <span className="req">*</span></label>
            <input
              className={fieldClass('input', 'geography')}
              value={form.geography}
              onChange={(e) => onField('geography', e.target.value)}
              placeholder="e.g. Vietnam · Southeast Asia"
            />
            {showErrors && !validity.geography && (
              <div className="field-error">This field is required.</div>
            )}
          </div>
        </div>

        <div className="vn-form-grid rise">
          <div>
            <label className="label">
              Country <span className="vn-form-sector-hint">· optional</span>
            </label>
            <input
              className="input"
              value={form.country}
              onChange={(e) => onField('country', e.target.value)}
              placeholder="e.g. Vietnam"
            />
          </div>
          <div>
            <label className="label">
              Target region <span className="vn-form-sector-hint">· optional</span>
            </label>
            <input
              className="input"
              value={form.targetRegion}
              onChange={(e) => onField('targetRegion', e.target.value)}
              placeholder="e.g. Southeast Asia"
            />
          </div>
        </div>

        <div className="vn-form-grid rise">
          <div>
            <label className="label">
              Number of employees <span className="vn-form-sector-hint">· optional</span>
            </label>
            <input
              type="number"
              min="0"
              className="input"
              value={form.numEmployees}
              onChange={(e) => onField('numEmployees', e.target.value)}
              placeholder="e.g. 12"
            />
          </div>
          <div>
            <label className="label">
              ARR (USD) <span className="vn-form-sector-hint">· optional</span>
            </label>
            <input
              type="number"
              min="0"
              className="input"
              value={form.arr}
              onChange={(e) => onField('arr', e.target.value)}
              placeholder="e.g. 250000"
            />
          </div>
        </div>

        <div className="rise">
          <label className="label">
            Sectors <span className="req">*</span>{' '}
            <span className="vn-form-sector-hint">· choose one or more</span>
          </label>
          <div className="vn-form-sector-wrap">
            {SECTORS.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`chip${form.sectors.includes(s.id) ? ' on' : ''}`}
                onClick={() => onToggleSector(s.id)}
              >
                {s.label}
              </button>
            ))}
          </div>
          {showErrors && !validity.sectors && (
            <div className="field-error" style={{ marginTop: 8 }}>Select at least one sector.</div>
          )}
        </div>

        <div className="rise">
          <label className="label">{needLabel} <span className="req">*</span></label>
          <textarea
            className={fieldClass('textarea', 'need')}
            value={form.need}
            onChange={(e) => onField('need', e.target.value)}
            placeholder={needPlaceholder}
          />
          {showErrors && !validity.need && (
            <div className="field-error">This field is required.</div>
          )}
        </div>

        <label
          className={`vn-form-consent rise${showErrors && !validity.consent ? ' invalid' : ''}${form.consent ? ' checked' : ''}`}
        >
          <input
            type="checkbox"
            className="vn-form-consent-checkbox"
            checked={form.consent}
            onChange={(e) => onField('consent', e.target.checked)}
          />
          <span className="vn-form-consent-text">
            I consent to VietNexus using this profile to generate explainable matches, and to sharing it with NIC when I request an introduction. <span className="req">*</span>
          </span>
        </label>
        {showErrors && !validity.consent && (
          <div className="vn-form-consent-error">Consent is required before your profile can be Ready.</div>
        )}

        {showSummary && (
          <div className="vn-form-summary rise">
            <div className="vn-form-summary-title">{missing.length} thing(s) still needed before Ready</div>
            <div className="vn-form-summary-text">Still needed: {missing.join(', ')}.</div>
          </div>
        )}

        <div className="vn-form-footer rise">
          <span className="vn-form-helper">{helperText}</span>
          <div className="vn-form-footer-actions">
            <button type="button" className="btn btn-ghost" onClick={onSaveDraft}>
              Save draft
            </button>
            <button
              type="button"
              className="btn btn-primary"
              style={{ opacity: (ready || allValid) ? 1 : 0.55 }}
              disabled={saving}
              onClick={onReady}
            >
              {readyLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
