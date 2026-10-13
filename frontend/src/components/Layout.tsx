import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useI18n } from '../i18n/i18n';
import { useAuth } from '../hooks/useAuth';

const links = [
  ['/pool', 'nav.pool'], ['/muar', 'nav.muar'], ['/scene', 'nav.scene'], ['/act', 'nav.acts'],
  ['/plays', 'nav.plays'], ['/ai', 'nav.ai'], ['/stage', 'nav.stage'], ['/me', 'nav.me'],
] as const;

export default function Layout() {
  const { t, lang, setLang } = useI18n();
  const { user } = useAuth();
  return (
    <>
      <header className="topbar">
        <div className="wrap row">
          <NavLink to="/" className="logo">RTD<em>.MUAR</em></NavLink>
          <nav className="nav">
            {links.map(([p, k]) => <NavLink key={p} to={p} className={({ isActive }) => isActive ? 'active' : ''}>{t(k)}</NavLink>)}
          </nav>
          <div className="row-flex" style={{ gap: 10 }}>
            <div className="lang">
              <button className={lang === 'ru' ? 'on' : ''} onClick={() => setLang('ru')}>RU</button>
              <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')}>EN</button>
            </div>
            {user && <span className="badge gold">{user.display_name || user.email}</span>}
          </div>
        </div>
      </header>
      <main><Outlet /></main>
      <nav className="bottom-nav">
        {links.map(([p, k]) => <NavLink key={p} to={p} className={({ isActive }) => isActive ? 'active' : ''}>{t(k)}</NavLink>)}
      </nav>
    </>
  );
}
