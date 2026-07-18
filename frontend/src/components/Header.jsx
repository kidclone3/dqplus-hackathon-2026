// Platform dashboard (ai-data-platform read API). Admin-gated server-side: the
// link hands over the JWT via ?token=, the API verifies role=admin and sets a cookie.
// Local dev hits :8000 directly; on the public site the VPS nginx mounts it at /agent.
const DASHBOARD_URL =
  import.meta.env.VITE_DASHBOARD_URL ||
  (['localhost', '127.0.0.1'].includes(window.location.hostname) ? 'http://localhost:8000' : '/agent');

export default function Header({ session, status, onLogout }) {
  const ready = status === 'ready';
  const isAdmin = session.user.role === 'admin';
  return (
    <header className="vn-header">
      <div className="vn-header-brand">
        <img className="vn-header-logo" src="/logo.png" alt="VietNexus" />
        <b className="vn-header-name">VietNexus</b>
      </div>
      <div className="vn-header-right">
        {isAdmin && (
          <a
            className="btn btn-ghost vn-header-dashboard"
            href={DASHBOARD_URL + '/?token=' + encodeURIComponent(session.token)}
            target="_blank"
            rel="noreferrer"
          >
            Dashboard
          </a>
        )}
        <span className={'vn-header-status ' + (ready ? 'ready' : 'draft')}>
          <i className="dot" aria-hidden="true" />
          {ready ? 'Ready' : 'Draft'}
        </span>
        <span className="vn-header-email">{session.user.username}</span>
        <button type="button" className="btn btn-ghost vn-header-logout" onClick={onLogout}>
          Log out
        </button>
      </div>
    </header>
  );
}
