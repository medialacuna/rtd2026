import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { useI18n } from '../i18n/i18n';

export default function Ai() {
  const { t } = useI18n();
  const [mem, setMem] = useState<any[]>([]); const [q, setQ] = useState(''); const [answer, setAnswer] = useState(''); const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<any>(null);
  useEffect(() => { api.aiMemory().then(r => setMem(Array.isArray(r) ? r : [])).catch(() => {}); api.health().then(setHealth).catch(() => {}); }, []);
  const ask = async (e: React.FormEvent) => { e.preventDefault(); if (!q.trim()) return; setBusy(true); setAnswer('');
    try { const r = await api.aiAsk(q.trim()); setAnswer(r.answer || JSON.stringify(r)); } catch (er: any) { setAnswer(er.message); } finally { setBusy(false); } };
  const typeBadge: Record<string, string> = { learned: 'green', question: 'gold', gap: '', summary: 'gold' };
  return (
    <div className="wrap">
      <div className="kicker">{t('ai.witness')}</div>
      <h1 className="page-title">{t('nav.ai')}</h1>
      {health && <p className="page-sub">Зрелость ИИ: {health.maturity_score}/100 · модель {health.model} · Ollama {health.ollama ? 'on' : 'off'}</p>}
      <form className="join-card" onSubmit={ask} style={{ margin: '26px auto 0', maxWidth: 640 }}>
        <div className="field"><input value={q} placeholder="Спроси свидетеля: что такое муар? кто такой идиот на третьей ступени?" onChange={e => setQ(e.target.value)} /></div>
        <div className="spacer" /><button className="btn" disabled={busy}>{busy ? 'думает…' : 'Спросить'}</button>
        {answer && <p className="stage-answer" style={{ textAlign: 'left' }}>{answer}</p>}
      </form>
      <hr className="hr" />
      <div className="kicker">память · что я понял / не понял / спросил</div>
      <ul className="plain">
        {mem.map(m => (
          <li className="replica" key={m.id}>
            <div className="grow">
              <span className={`badge ${typeBadge[m.type] || ''}`}>{m.type}</span>
              <div style={{ marginTop: 8, fontFamily: 'var(--serif)', fontSize: 16 }}>{m.content}</div>
              <div className="meta"><span>{m.source}</span><span>conf {Number(m.confidence ?? 0).toFixed(2)}</span><span>{new Date(m.learned_at).toLocaleString()}</span></div>
            </div>
          </li>
        ))}
        {mem.length === 0 && <p className="page-sub">Память пуста. ИИ ещё ничему не научился вслух.</p>}
      </ul>
    </div>
  );
}
