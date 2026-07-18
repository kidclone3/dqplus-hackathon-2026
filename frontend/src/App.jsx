import { useState, useEffect, useRef } from 'react';
import Header from './components/Header.jsx';
import AuthGate from './views/AuthGate.jsx';
import ProfileForm from './views/ProfileForm.jsx';
import Matches from './views/Matches.jsx';
import MatchDetail from './views/MatchDetail.jsx';
import { DATASETS, STARTUPS, INTENTS } from './data/ecosystem.js';
import { genDraft } from './lib/draft.js';
import { getProfile, saveProfile, toProfilePayload, fromProfile, ApiError } from './lib/api.js';

const SESSION_KEY = 'vn.session';

const emptyForm = {
  name: '', website: '', stage: '', geography: '', country: '', targetRegion: '',
  numEmployees: '', arr: '', sectors: [], need: '', consent: false,
};

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
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
  const [selCandidate, setSelCandidate] = useState(null);
  const [emailLang, setEmailLang] = useState('vi');
  const [copied, setCopied] = useState(false);

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
    if (s.user.profileId && !s.demo) {
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
        });
    } else if (mirror) {
      setForm(mirror.form);
      setStatus(mirror.status || 'draft');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleAuthed(newSession) {
    setSession(newSession);
    persistSession(newSession);
    if (newSession.user.profileId && !newSession.demo) {
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
        });
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
    return {
      name: f.name.trim().length > 1,
      website: /\./.test(f.website.trim()) && f.website.trim().length > 3,
      stage: !!f.stage,
      geography: f.geography.trim().length > 1,
      sectors: f.sectors.length > 0,
      need: f.need.trim().length > 2,
      consent: f.consent === true,
    };
  }

  const v = validity(form);
  const allValid = Object.values(v).every(Boolean);
  const missingMap = {
    name: role === 'investor' ? 'fund name' : 'startup name',
    website: 'website',
    stage: role === 'investor' ? 'stage focus' : 'stage',
    geography: 'geography',
    sectors: 'sectors',
    need: role === 'investor' ? 'collaboration need' : 'funding need',
    consent: 'consent',
  };
  const missing = Object.keys(v).filter((k) => !v[k]).map((k) => missingMap[k]);

  async function persist(nextStatus) {
    persistProfileMirror(session.user.username, form, nextStatus);
    if (session.demo) return;
    setSaving(true);
    setSaveError('');
    try {
      const saved = await saveProfile(session.token, session.user.profileId, toProfilePayload(form));
      if (saved && saved.id && saved.id !== session.user.profileId) {
        const next = { ...session, user: { ...session.user, profileId: saved.id } };
        setSession(next);
        persistSession(next);
      }
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : "Couldn't reach the server. Your draft is saved locally.");
    } finally {
      setSaving(false);
    }
  }

  function saveDraft() {
    setStatus('draft');
    setSavedAt(Date.now());
    persist('draft');
  }

  function markReady() {
    if (allValid) {
      setStatus('ready');
      setShowErrors(false);
      setView('matches');
      persist('ready');
    } else {
      setShowErrors(true);
    }
  }

  function logout() {
    setSession(null);
    persistSession(null);
  }

  if (!session) {
    return <AuthGate onAuthed={handleAuthed} />;
  }

  const active = intent === 'investors' && role === 'investor' ? STARTUPS : DATASETS[intent];
  const sorted = [...active].sort((a, b) => b.score - a.score);
  const shown = topK >= sorted.length ? sorted : sorted.slice(0, topK);
  const items = shown.map((c) => ({ candidate: c, rank: sorted.indexOf(c) + 1 }));

  const profileName = form.name || (role === 'investor' ? 'your fund' : 'your startup');
  const metaCur = INTENTS.find((i) => i.id === intent) || INTENTS[0];
  const title = intent === 'investors' && role === 'investor' ? 'Startups that fit your thesis.' : metaCur.title;
  const sub = (intent === 'investors' && role === 'investor' ? 'Startups in {p}’s focus, ranked by fit.' : metaCur.sub).replace('{p}', profileName);

  function openMatch(item) {
    setSelCandidate(item.candidate);
    setCopied(false);
    setView('detail');
  }

  function onIntentChange(id) {
    setIntent(id);
    setTopK(5);
    setSelCandidate(null);
    setCopied(false);
  }

  function draftTextFor(candidate) {
    if (!candidate || candidate.draftError) return null;
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

  const cand = selCandidate || sorted[0];
  const candRank = cand ? sorted.indexOf(cand) + 1 : 0;

  return (
    <div className="vn-shell">
      <Header session={session} status={status} onLogout={logout} />
      {view === 'form' && (
        <ProfileForm
          role={role}
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
          onIntent={onIntentChange}
          topK={topK}
          onTopK={setTopK}
          items={items}
          total={sorted.length}
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
    </div>
  );
}
