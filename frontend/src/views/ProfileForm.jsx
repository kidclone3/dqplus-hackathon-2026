import { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import { SECTORS, STAGES } from '../data/ecosystem.js';
import { riseIn } from '../lib/anim.js';
import './form.css';

export default function ProfileForm({
  role,
  hydrating,
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
  const needPlaceholder = isInvestor
    ? 'What partnerships or deal flow are you looking for?'
    : 'What collaboration or funding are you looking for?';
  const showSummary = showErrors && !allValid;

  let helperText;
  if (saving) {
    helperText = 'Saving…';
  } else if (ready) {
    helperText = 'Your profile is Ready for matching.';
  } else if (saveError) {
    helperText = saveError;
  } else if (savedAt) {
    helperText = 'Draft saved.';
  } else {
    helperText = 'Draft: not yet visible for matching.';
  }

  const readyLabel = ready ? 'See matches' : 'Mark as Ready';

  const fieldClass = (base, key) => `${base}${showErrors && !validity[key] ? ' invalid' : ''}`;

  // Saved profile still loading: real header, skeleton fields (mirrors the form shape).
  if (hydrating) {
    return (
      <div className="vn-form-container" aria-busy="true">
        <div className="eyebrow">Your profile · one form</div>
        <h1 className="serif-h1 vn-form-title">Tell the ecosystem who you are.</h1>
        <p className="lede vn-form-lede">Loading your saved profile.</p>
        <div className="vn-form-skeleton">
          {[0, 1, 2].map((row) => (
            <div className="vn-form-skel-grid" key={row}>
              <div>
                <span className="vn-skel vn-form-skel-label" />
                <span className="vn-skel vn-form-skel-input" />
              </div>
              <div>
                <span className="vn-skel vn-form-skel-label" />
                <span className="vn-skel vn-form-skel-input" />
              </div>
            </div>
          ))}
          <span className="vn-skel vn-form-skel-label" />
          <span className="vn-skel vn-form-skel-area" />
        </div>
      </div>
    );
  }

  return (
    <div ref={rootRef} className="vn-form-container">
      <div className="eyebrow rise">Your profile · one form</div>
      <h1 className="serif-h1 vn-form-title rise">Tell the ecosystem who you are.</h1>
      <p className="lede vn-form-lede rise">
        One calm form. Save a draft anytime, your profile only becomes <b>Ready</b> for matching once the essentials check out.
      </p>

      <div className="vn-form-role rise">
        <span className="chip on vn-form-role-badge">
          {isInvestor ? 'Investor' : 'Startup'} account
        </span>
      </div>

      <div className="vn-form-fields">
        <div className="vn-form-section">
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
                placeholder="https://example.com"
              />
              {showErrors && !validity.website && (
                <div className="field-error">Enter a valid website URL.</div>
              )}
            </div>
          </div>

          <div className="vn-form-grid rise">
            <div>
              <label className="label">Stage focus <span className="req">*</span></label>
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
              <label className="label">Geography <span className="req">*</span></label>
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
              <label className="label">Email <span className="req">*</span></label>
              <input
                type="email"
                className={fieldClass('input', 'email')}
                value={form.email}
                onChange={(e) => onField('email', e.target.value)}
                placeholder="e.g. hello@example.com"
              />
              {showErrors && !validity.email && (
                <div className="field-error">Enter a valid email address.</div>
              )}
            </div>
            <div>
              <label className="label">Phone number <span className="req">*</span></label>
              <input
                type="tel"
                className={fieldClass('input', 'phone')}
                value={form.phone}
                onChange={(e) => onField('phone', e.target.value)}
                placeholder="e.g. +84 90 123 4567"
              />
              {showErrors && !validity.phone && (
                <div className="field-error">Enter a valid phone number.</div>
              )}
            </div>
          </div>
        </div>

        <div className="vn-form-section">
          <div className="vn-form-section-cap rise">
            {isInvestor ? 'Investor profile' : 'Company profile'}
          </div>
          {isInvestor ? (
            <>
              <div className="vn-form-grid rise">
                <div>
                  <label className="label">Average initial investment (USD) <span className="req">*</span></label>
                  <input
                    type="number"
                    min="0"
                    className={fieldClass('input', 'avgInitialInvestment')}
                    value={form.avgInitialInvestment}
                    onChange={(e) => onField('avgInitialInvestment', e.target.value)}
                    placeholder="e.g. 500000"
                  />
                  {showErrors && !validity.avgInitialInvestment && (
                    <div className="field-error">Enter a valid amount.</div>
                  )}
                </div>
                <div>
                  <label className="label">Annual investment number <span className="req">*</span></label>
                  <input
                    type="number"
                    min="0"
                    className={fieldClass('input', 'annualInvestmentCount')}
                    value={form.annualInvestmentCount}
                    onChange={(e) => onField('annualInvestmentCount', e.target.value)}
                    placeholder="e.g. 10"
                  />
                  {showErrors && !validity.annualInvestmentCount && (
                    <div className="field-error">Enter a valid number.</div>
                  )}
                </div>
              </div>

              <div className="rise">
                <div>
                  <label className="label">Average startup holding period (years) <span className="req">*</span></label>
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    className={fieldClass('input', 'avgHoldingPeriod')}
                    value={form.avgHoldingPeriod}
                    onChange={(e) => onField('avgHoldingPeriod', e.target.value)}
                    placeholder="e.g. 5"
                  />
                  {showErrors && !validity.avgHoldingPeriod && (
                    <div className="field-error">Enter a valid number of years.</div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="vn-form-grid rise">
              <div>
                <label className="label">Year founded <span className="req">*</span></label>
                <input
                  type="number"
                  min="1900"
                  max="2100"
                  className={fieldClass('input', 'yearFounded')}
                  value={form.yearFounded}
                  onChange={(e) => onField('yearFounded', e.target.value)}
                  placeholder="e.g. 2021"
                />
                {showErrors && !validity.yearFounded && (
                  <div className="field-error">Enter a 4-digit year.</div>
                )}
              </div>
              <div>
                <label className="label">Company size <span className="req">*</span></label>
                <input
                  type="number"
                  min="1"
                  className={fieldClass('input', 'companySize')}
                  value={form.companySize}
                  onChange={(e) => onField('companySize', e.target.value)}
                  placeholder="e.g. 12"
                />
                {showErrors && !validity.companySize && (
                  <div className="field-error">Enter the number of employees.</div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="vn-form-section">
          <div className="vn-form-section-cap rise">What you are looking for</div>
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
              <div className="field-error">Select at least one sector.</div>
            )}
          </div>

          <div className="rise">
            <label className="label">Collaboration need <span className="req">*</span></label>
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
          <span className={`vn-form-helper${saveError && !saving ? ' error' : ''}`}>{helperText}</span>
          <div className="vn-form-footer-actions">
            <button type="button" className="btn btn-ghost" disabled={saving} onClick={onSaveDraft}>
              Save draft
            </button>
            <button
              type="button"
              className={`btn btn-primary${(ready || allValid) ? '' : ' vn-form-cta-muted'}`}
              disabled={saving}
              onClick={onReady}
            >
              {readyLabel}
              {ready && <span className="vn-form-cta-arrow" aria-hidden="true">→</span>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
