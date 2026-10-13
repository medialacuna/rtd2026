import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../hooks/useAuth';
import { useI18n } from '../i18n/i18n';

export default function Join() {
  const { t } = useI18n(); const { login, user } = useAuth(); const nav = useNavigate();
  const [sp] = useSearchParams(); const [email, setEmail] = useState('');
  const [msg, setMsg] = useState(''); const [devLink, setDevLink] = useState(''); const [busy, setBusy] = useState(false);

  useEffect(() => { const tk = sp.get('token'); if (tk) {
    api.verify(tk).then(r => { login(r.token); nav('/pool'); }).catch(e => setMsg(String(e.message || e)));
  } }, [sp]);
  useEffect(() => { if (user) nav('/pool'); }, [user]);

  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setMsg('');
    try { const r = await api.requestLink(email);
      setMsg(r.sent ? t('join.sent') : `${t('join.devlink')} ${r.dev_link}`); if (r.dev_link) setDevLink(r.dev_link);
    } catch (err: any) { setMsg(err.message); } finally { setBusy(false); } };

  return (
    <div className="wrap hero fade-in">
      <div className="kicker">rtd.heartwins.ru · Real Time Drama</div>
      <h1>МУАР<br /><span>из реплик</span></h1>
      <p className="page-sub" style={{ margin: '18px auto 0' }}>{t('join.sub')}<br />{t('tagline')}</p>
      {!devLink && !msg.includes('http') ? (
        <form className="card join-card" onSubmit={submit}>
          <div className="kicker">{t('join.title')}</div>
          <div className="field"><input type="email" required placeholder={t('join.email')} value={email} onChange={e => setEmail(e.target.value)} /></div>
          <div className="spacer" />
          <button className="btn" style={{ width: '100%' }} disabled={busy}>{t('join.btn')}</button>
          {msg && <p style={{ marginTop: 14, fontSize: 13, color: 'var(--dim)' }}>{msg}</p>}
        </form>
      ) : (
        <div className="card join-card">
          <div className="kicker">{t('join.devlink')}</div>
          <a className="btn" href={devLink.replace(/.*?(\/verify\?token=.*)$/, '$1')} style={{ width: '100%' }}>Войти →</a>
        </div>
      )}
    </div>
  );
}
