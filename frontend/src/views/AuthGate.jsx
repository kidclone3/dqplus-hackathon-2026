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
  const [busy, setBusy] = useState(false);

  useGSAP(() => {
    if (rootRef.current) riseIn(rootRef.current);
  }, { scope: rootRef });

  const authTitle = mode === 'login' ? 'Enter the ecosystem' : 'Create your account';
  const authCta = mode === 'login' ? 'Sign in' : 'Create account';
  const authBusyCta = mode === 'login' ? 'Signing in...' : 'Creating account...';
  const authSwitchText = mode === 'login' ? 'New to VietNexus?' : 'Already have an account?';
  const authSwitchLink = mode === 'login' ? 'Create an account' : 'Sign in';

  function toggleMode() {
    setMode((m) => (m === 'login' ? 'register' : 'login'));
    setError('');
  }

  async function doAuth() {
    if (!email.trim() || !password.trim()) {
      setError('Enter your email and password to continue.');
      return;
    }
    setError('');
    setBusy(true);
    try {
      const { user, token } =
        mode === 'login'
          ? await login({ email, password })
          : await register({ email, password, role });
      onAuthed({
        token,
        user: { id: user.id, username: user.username, role: user.role, profileId: user.profileId },
      });
    } catch (e) {
      if (isNetworkError(e)) {
        setError("Can't reach the VietNexus server. Please try again.");
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

  return (
    <div className="vn-auth-page" ref={rootRef}>
      <div className="vn-auth-col">
        <div className="vn-auth-logo rise">
          <img className="vn-auth-tile" src="/logo.png" alt="VietNexus" />
          <span className="vn-auth-lockup">
            <b>VietNexus</b>
            <small>INNOVATION OS</small>
          </span>
        </div>

        <span className="eyebrow vn-auth-eyebrow rise">Private ecosystem</span>
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

          {error && (
            <div className="vn-auth-error" role="alert" aria-live="polite">
              {error}
            </div>
          )}

          <button
            type="button"
            className="btn btn-primary vn-auth-cta"
            onClick={doAuth}
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? authBusyCta : authCta}
          </button>

          <div className="vn-auth-switch">
            {authSwitchText} <a onClick={toggleMode}>{authSwitchLink}</a>
          </div>
        </div>

        <p className="vn-auth-footer rise">
          Your session is private. Draft data stays with your account.
        </p>
      </div>
    </div>
  );
}
