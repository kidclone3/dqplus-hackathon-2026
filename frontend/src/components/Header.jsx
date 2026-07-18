export default function Header({ session, status, onLogout }) {
  const ready = status === 'ready';
  return (
    <header className="vn-header">
      <div className="vn-header-brand">
        <span className="vn-header-tile">V</span>
        <b className="vn-header-name">VietNexus</b>
      </div>
      <div className="vn-header-right">
        <span className={'vn-header-status ' + (ready ? 'ready' : 'draft')}>
          {ready ? '● Ready' : '○ Draft'}
        </span>
        <span className="vn-header-email">{session.user.username}</span>
        <button type="button" className="btn btn-ghost vn-header-logout" onClick={onLogout}>
          Log out
        </button>
      </div>
    </header>
  );
}
