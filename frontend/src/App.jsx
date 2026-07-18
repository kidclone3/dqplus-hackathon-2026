import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import Header from './components/Header.jsx';
import Landing from './views/Landing.jsx';

// Views behind the landing are lazy: smaller first paint, chunks load on demand.
const AuthGate = lazy(() => import('./views/AuthGate.jsx'));
const ProfileForm = lazy(() => import('./views/ProfileForm.jsx'));
const Matches = lazy(() => import('./views/Matches.jsx'));
const MatchDetail = lazy(() => import('./views/MatchDetail.jsx'));

// Quiet page-header ghost shown while a lazy view chunk loads (no spinner).
function ViewFallback() {
  return (
    <div className="vn-view-loading" aria-busy="true" aria-label="Loading">
      <span className="vn-skel vn-skel-eyebrow" />
      <span className="vn-skel vn-skel-title" />
      <span className="vn-skel vn-skel-lede" />
    </div>
  );
}
import { INTENTS } from './data/ecosystem.js';
import { genDraft } from './lib/draft.js';
import {
  getProfile, saveProfile, toProfilePayload, fromProfile,
  getMatches, extractProfile, matchToCandidate, ApiError,
} from './lib/api.js';

const SESSION_KEY = 'vn.session';

const emptyForm = {
  name: '', website: '', stage: '', geography: '', sectors: [], need: '',
  email: '', phone: '',
  avgInitialInvestment: '', annualInvestmentCount: '', avgHoldingPeriod: '',
  yearFounded: '', companySize: '',
  consent: false,
};

const idleMatches = { status: 'idle', candidates: [], error: '' };

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    const s = raw ? JSON.parse(raw) : null;
    // Older sessions (or demo-mode ones) lack the user id the matching engine needs.
    if (!s || !s.token || !s.user || !s.user.id) return null;
    return s;
  } catch (e) {
    return null;
  }
}

function persistSession(session) {
  try {
    if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else localStorage.removeItem(SESSION_KEY);
  } catch (e) {}
}

function loadProfileMirror(username) {
  try {
    const raw = localStorage.getItem('vn.profile.' + username);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function persistProfileMirror(username, form, status) {
  try {
    localStorage.setItem('vn.profile.' + username, JSON.stringify({ form, status }));
  } catch (e) {}
}

export default function App() {
  const [session, setSession] = useState(() => loadSession());
  const [entered, setEntered] = useState(false);
  const role = session && session.user.role === 'investor' ? 'investor' : 'startup';
  const [form, setForm] = useState(emptyForm);
  const [status, setStatus] = useState('draft');
  const [savedAt, setSavedAt] = useState(0);
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [view, setView] = useState('form');
  const [intent, setIntent] = useState('investors');
  const [topK, setTopK] = useState(5);
  // Client-side match filters over the loaded candidate list ('all' = off).
  const [matchFilter, setMatchFilter] = useState({ type: 'all', sector: 'all' });
  const [matchData, setMatchData] = useState(idleMatches);
  const [selCandidate, setSelCandidate] = useState(null);
  const [emailLang, setEmailLang] = useState('vi');
  const [copied, setCopied] = useState(false);

  // True while the saved profile is being fetched on first load; the form shows
  // a skeleton instead of empty fields that pop in.
  const [hydrating, setHydrating] = useState(() => {
    const s = loadSession();
    return !!(s && s.user.profileId);
  });

  const hydrated = useRef(false);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [view]);

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;
    const s = session;
    if (!s) return;
    const mirror = loadProfileMirror(s.user.username);
    if (s.user.profileId) {
      getProfile(s.token, s.user.profileId)
        .then((p) => {
          let f = fromProfile(p);
          let st = 'draft';
          if (mirror) {
            f = { ...f, consent: mirror.form.consent };
            st = mirror.status || st;
          }
          setForm(f);
          setStatus(st);
        })
        .catch((e) => {
          if (e instanceof ApiError && e.status === 401) {
            setSession(null);
            persistSession(null);
          }
        })
        .finally(() => setHydrating(false));
    } else if (mirror) {
      setForm({ ...emptyForm, ...mirror.form });
      setStatus(mirror.status || 'draft');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadMatches() {
    setMatchData({ status: 'loading', candidates: [], error: '' });
    try {
      let data;
      try {
        data = await getMatches({ userId: session.user.id, role });
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          // No extracted profile yet — build one from the saved profile, then retry.
          await extractProfile(session.user.id);
          data = await getMatches({ userId: session.user.id, role });
        } else {
          throw e;
        }
      }
      setMatchData({
        status: 'ready',
        candidates: (data.matches || []).map((m) => matchToCandidate(m)),
        error: '',
      });
    } catch (e) {
      setMatchData({
        status: 'error',
        candidates: [],
        error: e instanceof ApiError ? e.message : "Couldn't reach the matching service.",
      });
    }
  }

  const intentMeta = INTENTS.find((i) => i.id === intent) || INTENTS[0];

  useEffect(() => {
    if (view !== 'form' && intentMeta.live && matchData.status === 'idle' && session) {
      loadMatches();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, intent, matchData.status]);

  function handleAuthed(newSession) {
    setSession(newSession);
    persistSession(newSession);
    setMatchData(idleMatches);
    if (newSession.user.profileId) {
      setHydrating(true);
      getProfile(newSession.token, newSession.user.profileId)
        .then((p) => {
          setForm({ ...fromProfile(p), consent: false });
          setStatus('draft');
        })
        .catch((e) => {
          if (e instanceof ApiError && e.status === 401) {
            setSession(null);
            persistSession(null);
          }
        })
        .finally(() => setHydrating(false));
    }
  }

  function setField(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
    setStatus('draft');
    setSavedAt(0);
  }

  function toggleSector(id) {
    setForm((f) => {
      const has = f.sectors.includes(id);
      return { ...f, sectors: has ? f.sectors.filter((x) => x !== id) : [...f.sectors, id] };
    });
    setStatus('draft');
    setSavedAt(0);
  }

  function validity(f) {
    const isNum = (val) => val !== '' && Number.isFinite(Number(val)) && Number(val) >= 0;
    return {
      name: f.name.trim().length > 1,
      website: /\./.test(f.website.trim()) && f.website.trim().length > 3,
      stage: !!f.stage,
      geography: f.geography.trim().length > 1,
      sectors: f.sectors.length > 0,
      need: f.need.trim().length > 2,
      email: /^\S+@\S+\.\S+$/.test(f.email.trim()),
      phone: f.phone.trim().length > 5,
      ...(role === 'investor'
        ? {
            avgInitialInvestment: isNum(f.avgInitialInvestment),
            annualInvestmentCount: isNum(f.annualInvestmentCount),
            avgHoldingPeriod: isNum(f.avgHoldingPeriod),
          }
        : {
            yearFounded: /^\d{4}$/.test(f.yearFounded.trim()),
            companySize: isNum(f.companySize) && Number(f.companySize) > 0,
          }),
      consent: f.consent === true,
    };
  }

  const v = validity(form);
  const allValid = Object.values(v).every(Boolean);
  const missingMap = {
    name: role === 'investor' ? 'fund name' : 'startup name',
    website: 'website',
    stage: 'stage focus',
    geography: 'geography',
    sectors: 'sector',
    need: 'collaboration need',
    email: 'email',
    phone: 'phone number',
    avgInitialInvestment: 'average initial investment',
    annualInvestmentCount: 'annual investment number',
    avgHoldingPeriod: 'average startup holding period',
    yearFounded: 'year founded',
    companySize: 'company size',
    consent: 'consent',
  };
  const missing = Object.keys(v).filter((k) => !v[k]).map((k) => missingMap[k]);

  async function persist(nextStatus) {
    persistProfileMirror(session.user.username, form, nextStatus);
    setSaving(true);
    setSaveError('');
    try {
      const saved = await saveProfile(session.token, session.user.profileId, toProfilePayload(form));
      if (saved && saved.id && saved.id !== session.user.profileId) {
        const next = { ...session, user: { ...session.user, profileId: saved.id } };
        setSession(next);
        persistSession(next);
      }
      return true;
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : "Couldn't reach the server. Your draft is saved locally.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  function saveDraft() {
    setStatus('draft');
    setSavedAt(Date.now());
    persist('draft');
  }

  async function markReady() {
    if (!allValid) {
      setShowErrors(true);
      return;
    }
    setStatus('ready');
    setShowErrors(false);
    const ok = await persist('ready');
    if (ok) {
      // Refresh the extracted profile + embedding so matches reflect the latest edits.
      try {
        await extractProfile(session.user.id);
      } catch (e) {}
    }
    setMatchData(idleMatches);
    setView('matches');
  }

  function logout() {
    setSession(null);
    persistSession(null);
    setMatchData(idleMatches);
    setForm(emptyForm);
    setView('form');
  }

  if (!session) {
    if (!entered) return <Landing onEnter={() => setEntered(true)} />;
    return (
      <Suspense fallback={<ViewFallback />}>
        <AuthGate onAuthed={handleAuthed} />
      </Suspense>
    );
  }

  const sorted = matchData.candidates;
  const typeOptions = [...new Set(sorted.map((c) => c.entityType))];
  const sectorOptions = [...new Set(sorted.flatMap((c) => c.sectors))].sort();
  const filtered = sorted.filter(
    (c) =>
      (matchFilter.type === 'all' || c.entityType === matchFilter.type) &&
      (matchFilter.sector === 'all' || c.sectors.includes(matchFilter.sector))
  );
  const shown = topK >= filtered.length ? filtered : filtered.slice(0, topK);
  const items = shown.map((c, i) => ({ candidate: c, rank: i + 1 }));

  const profileName = form.name || (role === 'investor' ? 'your fund' : 'your startup');
  const title = intent === 'investors' && role === 'investor' ? 'Startups that fit your thesis.' : intentMeta.title;
  const sub = (intent === 'investors' && role === 'investor' ? 'Startups in {p}’s focus, ranked by fit.' : intentMeta.sub).replace('{p}', profileName);

  function openMatch(item) {
    setSelCandidate(item.candidate);
    setCopied(false);
    setView('detail');
  }

  function onIntentChange(id) {
    setIntent(id);
    setTopK(5);
    setMatchFilter({ type: 'all', sector: 'all' });
    setSelCandidate(null);
    setCopied(false);
  }

  function draftTextFor(candidate) {
    if (!candidate) return null;
    return genDraft({
      who: form.name || (role === 'investor' ? 'our fund' : 'our startup'),
      need: form.need,
      candidate,
      lang: emailLang,
      intent,
    });
  }

  function onCopy() {
    const text = draftTextFor(selCandidate || sorted[0]);
    try {
      if (navigator.clipboard && text) navigator.clipboard.writeText(text);
    } catch (e) {}
    setCopied(true);
  }

  function onLang(lang) {
    setEmailLang(lang);
    setCopied(false);
  }

  const cand = selCandidate || filtered[0];
  const candRank = cand ? filtered.indexOf(cand) + 1 : 0;

  return (
    <div className="vn-shell">
      <Header session={session} status={status} onLogout={logout} />
      <Suspense fallback={<ViewFallback />}>
      {view === 'form' && (
        <ProfileForm
          role={role}
          hydrating={hydrating}
          form={form}
          onField={setField}
          onToggleSector={toggleSector}
          status={status}
          savedAt={savedAt}
          saving={saving}
          saveError={saveError}
          showErrors={showErrors}
          validity={v}
          missing={missing}
          onSaveDraft={saveDraft}
          onReady={markReady}
        />
      )}
      {view === 'matches' && (
        <Matches
          role={role}
          profileName={profileName}
          intent={intent}
          live={intentMeta.live}
          matchStatus={matchData.status}
          matchError={matchData.error}
          onRetry={loadMatches}
          onIntent={onIntentChange}
          topK={topK}
          onTopK={setTopK}
          filter={matchFilter}
          onFilter={setMatchFilter}
          typeOptions={typeOptions}
          sectorOptions={sectorOptions}
          items={items}
          total={filtered.length}
          title={title}
          sub={sub}
          onOpen={openMatch}
          onBackToForm={() => setView('form')}
        />
      )}
      {view === 'detail' && cand && (
        <MatchDetail
          candidate={cand}
          rank={candRank}
          intent={intent}
          emailLang={emailLang}
          onLang={onLang}
          copied={copied}
          onCopy={onCopy}
          draftText={draftTextFor(cand)}
          onBack={() => setView('matches')}
        />
      )}
      </Suspense>
    </div>
  );
}
