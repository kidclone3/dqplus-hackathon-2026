import { useRef, useState } from 'react';
import { useGSAP } from '@gsap/react';
import { login, register, isNetworkError } from '../lib/api.js';
import { riseIn } from '../lib/anim.js';
import './auth.css';

export default function AuthGate({ onAuthed }) {
  const rootRef = useRef(null);
  const [mode, setMode] = useState('login');
  const [role, setRole] = useState('startup');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [networkDown, setNetworkDown] = useState(false);
  const [busy, setBusy] = useState(false);

  useGSAP(() => {
    if (rootRef.current) riseIn(rootRef.current);
  }, { scope: rootRef });

  const authTitle = mode === 'login' ? 'Enter the ecosystem' : 'Create your account';
  const authCta = mode === 'login' ? 'Sign in' : 'Create account';
  const authSwitchText = mode === 'login' ? 'New to VietNexus?' : 'Already have an account?';
  const authSwitchLink = mode === 'login' ? 'Create an account' : 'Sign in';

  function toggleMode() {
    setMode((m) => (m === 'login' ? 'register' : 'login'));
    setError('');
    setNetworkDown(false);
  }

  async function doAuth() {
    if (!email.trim() || !password.trim()) {
      setError('Enter your email and password to continue.');
      return;
    }
    setError('');
    setNetworkDown(false);
    setBusy(true);
    try {
      const { user, token } =
        mode === 'login'
          ? await login({ email, password })
          : await register({ email, password, role });
      onAuthed({
        token,
        user: { username: user.username, role: user.role, profileId: user.profileId },
        demo: false,
      });
    } catch (e) {
      if (isNetworkError(e)) {
        setError("Can't reach the VietNexus server.");
        setNetworkDown(true);
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  function onPasswordKeyDown(e) {
    if (e.key === 'Enter') doAuth();
  }

  function continueDemo() {
    onAuthed({
      token: null,
      user: {
        username: email || 'founder@startup.vn',
        role: role === 'investor' ? 'investor' : 'founder',
        profileId: null,
      },
      demo: true,
    });
  }

  return (
    <div className="vn-auth-page" ref={rootRef}>
      <div className="vn-auth-col">
        <div className="vn-auth-logo rise">
          <span className="vn-auth-tile">V</span>
          <span className="vn-auth-lockup">
            <b>VietNexus</b>
            <small>INNOVATION OS</small>
          </span>
        </div>

        <h1 className="serif-h1 vn-auth-h1 rise">{authTitle}</h1>
        <p className="vn-auth-sub rise">
          The ecosystem is private. Sign in to view profiles, signals and matches.
        </p>

        <div className="card vn-auth-card rise">
          {mode === 'register' && (
            <div className="seg vn-auth-seg">
              <button
                type="button"
                className={`seg-btn ${role === 'startup' ? 'active' : ''}`}
                onClick={() => setRole('startup')}
              >
                Startup
              </button>
              <button
                type="button"
                className={`seg-btn ${role === 'investor' ? 'active' : ''}`}
                onClick={() => setRole('investor')}
              >
                Investor
              </button>
            </div>
          )}

          {error && <div className="vn-auth-error">{error}</div>}

          <label className="label">Email</label>
          <input
            type="email"
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@startup.vn"
          />

          <label className="label">Password</label>
          <input
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={onPasswordKeyDown}
            placeholder="Your password"
          />

          <button
            type="button"
            className="btn btn-primary vn-auth-cta"
            onClick={doAuth}
            disabled={busy}
          >
            {authCta}
          </button>

          {networkDown && (
            <button type="button" className="btn btn-ghost vn-auth-demo" onClick={continueDemo}>
              Continue in demo mode
            </button>
          )}

          <div className="vn-auth-switch">
            {authSwitchText} <a onClick={toggleMode}>{authSwitchLink}</a>
          </div>
        </div>

        <p className="vn-auth-footer rise">
          🔒 Your session is private. Draft data stays with your account.
        </p>
      </div>
    </div>
  );
}
