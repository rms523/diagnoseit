import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { IconLogo, NAV_ICONS, IconClose } from './Icons';

const NAV_ITEMS: Array<{ to: string; iconKey: string; label: string }> = [
  { to: '/', iconKey: 'dashboard', label: 'Dashboard' },
  { to: '/medical-reports', iconKey: 'reports', label: 'Medical Reports' },
  { to: '/symptoms', iconKey: 'symptoms', label: 'Symptoms' },
  { to: '/prescriptions', iconKey: 'prescriptions', label: 'Prescriptions' },
  { to: '/diagnosis', iconKey: 'diagnosis', label: 'Diagnosis' },
  { to: '/health-trends', iconKey: 'trends', label: 'Health Trends' },
  { to: '/lab-catalog', iconKey: 'catalog', label: 'Test Catalog' },
  { to: '/unit-converter', iconKey: 'converter', label: 'Unit Converter' },
  { to: '/profile', iconKey: 'profile', label: 'Profile' },
  { to: '/settings/ai', iconKey: 'settings', label: 'AI Settings' },
];

const Layout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const displayName = user?.first_name
    ? `${user.first_name} ${user.last_name || ''}`.trim()
    : user?.username;
  const initial = (user?.first_name?.[0] || user?.username?.[0] || '?').toUpperCase();

  return (
    <div className="layout">
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} aria-hidden />
      )}

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <IconLogo size={26} />
            <span className="sidebar-logo-text">DiagnoseIt</span>
          </div>
          <button className="sidebar-close btn-ghost" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
            <IconClose size={18} />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Main">
          {NAV_ITEMS.map((item) => {
            const Icon = NAV_ICONS[item.iconKey];
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="sidebar-link-icon"><Icon size={18} /></span>
                <span className="sidebar-link-label">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">{initial}</div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">{displayName}</div>
              <div className="sidebar-user-email">{user?.email}</div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm sidebar-logout" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="main-wrapper">
        <header className="topbar">
          <button className="topbar-menu btn-ghost" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            ☰
          </button>
          <span className="topbar-title">DiagnoseIt</span>
          <div className="topbar-avatar">{initial}</div>
        </header>

        <main className="main-content">
          <Outlet />
        </main>
      </div>

      <style>{`
        .layout { display: flex; min-height: 100vh; }

        .sidebar {
          width: var(--sidebar-width);
          min-height: 100vh;
          background: var(--paper-elevated);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          position: fixed;
          top: 0;
          left: 0;
          z-index: 100;
          transition: transform var(--transition-base);
        }

        .sidebar-overlay { display: none; }

        .sidebar-close {
          display: none;
          font-size: var(--font-lg);
          cursor: pointer;
          border: none;
          background: none;
          color: var(--text-secondary);
        }

        .sidebar-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--space-5) var(--space-5);
          border-bottom: 1px solid var(--border-color);
        }

        .sidebar-logo {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }

        .sidebar-logo-text {
          font-family: var(--font-display);
          font-size: var(--font-lg);
          font-weight: 600;
          color: var(--ink);
        }

        .sidebar-nav {
          flex: 1;
          padding: var(--space-4) var(--space-3);
          display: flex;
          flex-direction: column;
          gap: 2px;
          overflow-y: auto;
        }

        .sidebar-link {
          display: flex;
          align-items: center;
          gap: var(--space-3);
          padding: var(--space-3) var(--space-4);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: var(--font-sm);
          font-weight: 500;
          transition: all var(--transition-fast);
          text-decoration: none;
        }

        .sidebar-link:hover {
          background: var(--paper-muted);
          color: var(--text-primary);
        }

        .sidebar-link.active {
          background: var(--teal-dim);
          color: var(--teal);
        }

        .sidebar-link-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 20px;
          flex-shrink: 0;
        }

        .sidebar-footer {
          padding: var(--space-4);
          border-top: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          gap: var(--space-3);
        }

        .sidebar-user {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }

        .sidebar-avatar {
          width: 34px;
          height: 34px;
          border-radius: var(--radius-md);
          background: var(--teal);
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: var(--font-mono);
          font-size: var(--font-sm);
          font-weight: 500;
          color: #fff;
          flex-shrink: 0;
        }

        .sidebar-user-info { overflow: hidden; min-width: 0; }

        .sidebar-user-name {
          font-size: var(--font-sm);
          font-weight: 500;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .sidebar-user-email {
          font-family: var(--font-mono);
          font-size: 0.6875rem;
          color: var(--text-muted);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .sidebar-logout { width: 100%; justify-content: center; color: var(--text-muted); }

        .main-wrapper {
          flex: 1;
          margin-left: var(--sidebar-width);
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }

        .topbar { display: none; }

        .main-content {
          flex: 1;
          padding: var(--space-8) var(--space-10);
          max-width: 1120px;
          width: 100%;
          margin: 0 auto;
          animation: fadeIn 0.25s ease;
        }

        @media (max-width: 768px) {
          .sidebar { transform: translateX(-100%); box-shadow: var(--shadow-lg); }
          .sidebar.open { transform: translateX(0); }
          .sidebar-overlay {
            display: block;
            position: fixed;
            inset: 0;
            background: rgba(28, 35, 51, 0.3);
            z-index: 99;
            animation: fadeIn 0.15s ease;
          }
          .sidebar-close { display: block; }
          .main-wrapper { margin-left: 0; }
          .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-3) var(--space-4);
            border-bottom: 1px solid var(--border-color);
            background: var(--paper-elevated);
            position: sticky;
            top: 0;
            z-index: 50;
          }
          .topbar-menu {
            font-size: 1.25rem;
            cursor: pointer;
            border: none;
            background: none;
            color: var(--text-primary);
            padding: var(--space-2);
          }
          .topbar-title {
            font-family: var(--font-display);
            font-size: var(--font-lg);
            font-weight: 600;
            color: var(--ink);
          }
          .topbar-avatar {
            width: 30px;
            height: 30px;
            border-radius: var(--radius-md);
            background: var(--teal);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: var(--font-mono);
            font-size: var(--font-xs);
            font-weight: 500;
            color: #fff;
          }
          .main-content { padding: var(--space-5) var(--space-4); }
        }
      `}</style>
    </div>
  );
};

export default Layout;
