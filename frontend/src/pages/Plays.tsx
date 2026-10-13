import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { useI18n } from '../i18n/i18n';

const sectionRu: Record<string, string> = { lestnica: 'Лестница', genesis: 'Генезис', theories: 'Теории', muar: 'Муар' };

export default function Plays() {
  const { t } = useI18n();
  const [plays, setPlays] = useState<any[]>([]); const [open, setOpen] = useState<any>(null); const [text, setText] = useState('');
  useEffect(() => { api.plays().then(setPlays).catch(() => {}); }, []);
  const view = async (id: number) => { setOpen(await api.play(id)); setText(''); };
  return (
    <div className="wrap">
      <div className="kicker">komarovo series · rtd library</div>
      <h1 className="page-title">{t('plays.title')}</h1>
      <p className="page-sub">Пьесы, усвоенные ИИ. Каждая разбита на фрагменты и живёт в своём разделе знания.</p>
      <div className="spacer" />
      <div className="grid grid-3">
        {plays.map(p => (
          <div className="card play-card fade-in" key={p.id}>
            <div className="row-flex" style={{ justifyContent: 'space-between' }}>
              <span className="badge gold">{sectionRu[p.section] || p.section}</span>
              <span className="badge green">{t('plays.learned')} {p.learned_fragments}</span>
            </div>
            <div className="spacer" />
            <h3>{p.title}</h3>
            <p>{p.excerpt}</p>
            <div className="spacer" />
            <button className="btn ghost" onClick={() => view(p.id)}>Читать →</button>
          </div>
        ))}
      </div>
      {open && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', zIndex: 60, display: 'grid', placeItems: 'center', padding: 16 }}
             onClick={() => setOpen(null)}>
          <div className="card" style={{ maxWidth: 860, width: '100%', maxHeight: '88vh', display: 'flex', flexDirection: 'column' }} onClick={e => e.stopPropagation()}>
            <div className="row-flex" style={{ justifyContent: 'space-between' }}>
              <h3 style={{ fontFamily: 'var(--display)', fontWeight: 600 }}>{open.title}</h3>
              <button className="btn ghost" style={{ padding: '8px 16px' }} onClick={() => setOpen(null)}>✕</button>
            </div>
            <p style={{ color: 'var(--dim)', fontSize: 13, margin: '6px 0 14px' }}>{open.author} · {sectionRu[open.section]}</p>
            <div className="play-text">{open.content}</div>
          </div>
        </div>
      )}
    </div>
  );
}
