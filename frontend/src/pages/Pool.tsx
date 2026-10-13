import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../hooks/useAuth';
import { useI18n } from '../i18n/i18n';
import { useLive } from '../hooks/useLive';

export default function Pool() {
  const { t } = useI18n(); const { user } = useAuth();
  const [items, setItems] = useState<any[]>([]); const [sort, setSort] = useState('fresh');
  const [text, setText] = useState(''); const [tost, setTost] = useState(false); const [err, setErr] = useState('');
  const load = (s = sort) => api.replicas(s).then(r => setItems(Array.isArray(r) ? r : r.items || [])).catch(() => {});
  useEffect(() => { load(sort); }, [sort]);
  useLive(ev => {
    if (ev.event === 'replica:new') setItems(p => [ev.data, ...p.filter(x => x.id !== ev.data?.id)].slice(0, 60));
    if (ev.event === 'scene:new' || ev.event === 'scene:update') load();
  });
  const send = async (e?: React.FormEvent) => { e?.preventDefault(); if (!text.trim()) return; setErr('');
    try { await api.createReplica(text.trim(), tost); setText(''); load(); } catch (er: any) { setErr(er.message); } };

  return (
    <div className="wrap">
      <div className="kicker">realtime · <span className="live-dot pulse" /></div>
      <h1 className="page-title">{t('pool.title')}</h1>
      <div className="tabs">
        {[['fresh', t('pool.fresh')], ['resonant', t('pool.resonant')], ['contested', t('pool.contested')]].map(([k, l]) =>
          <button key={k} className={sort === k ? 'on' : ''} onClick={() => setSort(k)}>{l}</button>)}
      </div>
      {items.length === 0 && <p className="page-sub">Пул пуст. Начни игру — напиши первую реплику.</p>}
      {items.map(r => (
        <article className="replica fade-in" key={r.id}>
          <div className="avatar">{(r.step_level || '?').slice(0, 2).toUpperCase()}</div>
          <div className="grow">
            <div style={{ fontFamily: 'var(--serif)', fontSize: 18 }}>{r.text}</div>
            <div className="meta">
              <span>{r.display_name || 'участник'}</span><span>{r.step_function || r.step_level}</span>
              {r.is_tost && <span className="badge gold">тост</span>}
              <span className="mono">вес {Number(r.weight ?? 0).toFixed(2)}</span>
              <span>{new Date(r.created_at).toLocaleString()}</span>
              {user && r.user_id === user.id && <button style={{ color: 'var(--danger)', fontSize: 12 }} onClick={() => api.retract(r.id).then(() => load())}>отозвать</button>}
            </div>
          </div>
        </article>
      ))}
      {user && (
        <form className="composer" onSubmit={send}>
          <div className="inner">
            <textarea maxLength={280} value={text} placeholder={t('pool.placeholder')} onChange={e => setText(e.target.value)} rows={2} />
            <div style={{ display: 'grid', gap: 8 }}>
              <button className="btn" type="submit">{t('pool.send')}</button>
              <button className="btn ghost" type="button" onClick={() => setTost(v => !v)} style={{ padding: '8px 14px', fontSize: 12 }}>{t('pool.tost')}{tost ? ' ✓' : ''}</button>
            </div>
          </div>
          {err && <p style={{ fontSize: 12, color: 'var(--danger)', marginTop: 8 }}>{err}</p>}
        </form>
      )}
    </div>
  );
}
