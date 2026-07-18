import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as Clipboard from 'expo-clipboard';
import {
  CANDIDATES,
  DATASETS,
  INTENTS,
  SECTORS,
  STARTUPS,
  WHY_NOW_BY_INTENT,
  WHY_NOT_DEFAULT,
  genDraft,
} from '../data/mockData';
import { loadProfile, saveProfile } from '../services/storage';
import { colors } from '../theme/theme';

const AppContext = createContext(null);

const initialForm = {
  name: '',
  website: '',
  stage: '',
  geography: '',
  sectors: [],
  need: '',
  traction: '',
  consent: false,
};

export function AppProvider({ children }) {
  const [accent] = useState(colors.accent);
  const [authed, setAuthed] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');

  const [role, setRole] = useState(null);
  const [status, setStatus] = useState('draft');
  const [showErrors, setShowErrors] = useState(false);
  const [savedAt, setSavedAt] = useState(0);
  const [form, setForm] = useState(initialForm);

  const [intent, setIntent] = useState('investors');
  const [topK, setTopK] = useState(5);
  const [selCandidate, setSelCandidate] = useState(null);
  const [emailLang, setEmailLang] = useState('vi');
  const [copied, setCopied] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);

  const isInvestor = role === 'investor';

  useEffect(() => {
    let cancelled = false;
    loadProfile().then((saved) => {
      if (cancelled || !saved) {
        setProfileLoaded(true);
        return;
      }
      if (saved.role) setRole(saved.role);
      if (saved.form) setForm((f) => ({ ...f, ...saved.form }));
      if (saved.status) setStatus(saved.status);
      if (saved.savedAt) setSavedAt(saved.savedAt);
      setProfileLoaded(true);
    });
    return () => { cancelled = true; };
  }, []);

  const doAuth = useCallback(() => {
    if (!authEmail.trim() || !authPassword.trim()) {
      setAuthError('Enter your email and password to continue.');
      return;
    }
    setAuthError('');
    setAuthed(true);
    setRole((r) => r || 'startup');
  }, [authEmail, authPassword]);

  const logout = useCallback(() => {
    setAuthed(false);
    setAuthPassword('');
  }, []);

  const toggleAuthMode = useCallback(() => {
    setAuthMode((m) => (m === 'login' ? 'register' : 'login'));
    setAuthError('');
  }, []);

  const setField = useCallback((key, value) => {
    setForm((f) => ({ ...f, [key]: value }));
    setStatus('draft');
    setSavedAt(0);
  }, []);

  const toggleSector = useCallback((id) => {
    setForm((f) => {
      const has = f.sectors.includes(id);
      return { ...f, sectors: has ? f.sectors.filter((x) => x !== id) : [...f.sectors, id] };
    });
    setStatus('draft');
    setSavedAt(0);
  }, []);

  const chooseRole = useCallback((next) => {
    setRole(next);
    setStatus('draft');
    setSavedAt(0);
  }, []);

  const validity = useMemo(() => ({
    name: form.name.trim().length > 1,
    website: /\./.test(form.website.trim()) && form.website.trim().length > 3,
    stage: !!form.stage,
    geography: form.geography.trim().length > 1,
    sectors: form.sectors.length > 0,
    need: form.need.trim().length > 2,
    consent: form.consent === true,
  }), [form]);

  const allValid = useMemo(() => Object.values(validity).every(Boolean), [validity]);

  const missingLabels = useMemo(() => {
    const map = {
      name: isInvestor ? 'fund name' : 'startup name',
      website: 'website',
      stage: isInvestor ? 'stage focus' : 'stage',
      geography: 'geography',
      sectors: 'sectors',
      need: isInvestor ? 'collaboration need' : 'funding need',
      consent: 'consent',
    };
    return Object.keys(validity).filter((k) => !validity[k]).map((k) => map[k]);
  }, [validity, isInvestor]);

  const saveDraft = useCallback(() => {
    const savedTime = Date.now();
    setStatus('draft');
    setSavedAt(savedTime);
    saveProfile({ role, form, status: 'draft', savedAt: savedTime });
  }, [role, form]);

  const markReady = useCallback(() => {
    if (allValid) {
      setStatus('ready');
      setShowErrors(false);
      saveProfile({ role, form, status: 'ready', savedAt: Date.now() });
      return true;
    }
    setShowErrors(true);
    return false;
  }, [allValid, role, form]);

  const invSwap = isInvestor;
  const activeDataset = useMemo(() => {
    if (intent === 'investors' && invSwap) return STARTUPS;
    return DATASETS[intent] || CANDIDATES;
  }, [intent, invSwap]);

  const sorted = useMemo(
    () => activeDataset.slice().sort((a, b) => b.score - a.score),
    [activeDataset],
  );

  const shown = useMemo(
    () => (topK >= sorted.length ? sorted : sorted.slice(0, topK)),
    [sorted, topK],
  );

  const rankOf = useCallback((c) => sorted.indexOf(c) + 1, [sorted]);

  const openCandidate = useCallback((c) => {
    setSelCandidate(c);
    setCopied(false);
  }, []);

  const goIntent = useCallback((id) => {
    setIntent(id);
    setTopK(5);
    setSelCandidate(null);
    setCopied(false);
  }, []);

  const whoName = form.name || (isInvestor ? 'your fund' : 'your startup');

  const currentIntentMeta = useMemo(
    () => INTENTS.find((i) => i.id === intent) || INTENTS[0],
    [intent],
  );

  const matchTitle = intent === 'investors' && invSwap ? 'Startups that fit your thesis.' : currentIntentMeta.title;
  const matchSub = (intent === 'investors' && invSwap ? 'Startups in {p}’s focus, ranked by fit.' : currentIntentMeta.sub).replace('{p}', whoName);

  const detailFor = useCallback((cand) => {
    if (!cand) return null;
    const clamp = (n) => Math.max(0, Math.min(100, Math.round(n)));
    const breakdown = [
      { label: 'Sector fit', val: clamp(cand.score + 6) },
      { label: 'Stage fit', val: clamp(cand.score - 4) },
      { label: 'Geography', val: clamp(cand.score - 9) },
      { label: 'Thesis alignment', val: clamp(cand.score + 2) },
    ];
    const facts = [
      (intent === 'talent' ? 'Role · ' : 'Type · ') + cand.type,
      'Focus · ' + cand.sectors.join(', '),
      'Fit score · ' + cand.score + '/100',
      (cand.sources.length || 'No') + ' public source' + (cand.sources.length === 1 ? '' : 's') + ' checked',
    ];
    return {
      ...cand,
      hasSources: cand.sources.length > 0,
      noSources: cand.sources.length === 0,
      hasDraft: !cand.draftError,
      draft: cand.draftError ? '' : genDraft(cand, emailLang, intent, whoName, form.need),
      breakdown,
      whyNow: WHY_NOW_BY_INTENT[intent] || WHY_NOW_BY_INTENT.partners,
      whyNot: WHY_NOT_DEFAULT,
      facts,
      rank: rankOf(cand),
      confidencePct: clamp(cand.score - 2),
    };
  }, [emailLang, intent, whoName, form.need, rankOf]);

  const copyDraft = useCallback((text) => {
    Clipboard.setStringAsync(text).catch(() => {});
    setCopied(true);
  }, []);

  const value = useMemo(() => ({
    accent,
    authed, authMode, authEmail, authPassword, authError,
    setAuthEmail, setAuthPassword, doAuth, logout, toggleAuthMode,

    profileLoaded,
    role, isInvestor, chooseRole,
    status, showErrors, savedAt, allValid, validity, missingLabels,
    form, setField, toggleSector, saveDraft, markReady,

    intent, goIntent, topK, setTopK,
    sorted, shown, rankOf,
    selCandidate, openCandidate,
    emailLang, setEmailLang, copied, copyDraft,
    matchTitle, matchSub, whoName,
    detailFor,
    SECTORS,
  }), [
    accent, authed, authMode, authEmail, authPassword, authError, doAuth, logout, toggleAuthMode,
    profileLoaded,
    role, isInvestor, chooseRole,
    status, showErrors, savedAt, allValid, validity, missingLabels,
    form, setField, toggleSector, saveDraft, markReady,
    intent, goIntent, topK,
    sorted, shown, rankOf,
    selCandidate, openCandidate,
    emailLang, copied, copyDraft,
    matchTitle, matchSub, whoName,
    detailFor,
  ]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
