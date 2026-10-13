import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { useI18n } from '../i18n/i18n';
import { useLive } from '../hooks/useLive';

export default function Scene() {
  const { t } = useI18n();
  const [day, setDay] = useState<any>(null); const [all, setAll] = useState<any[]>([]);
  const load = () => { api.sceneOfDay().then(d => setDay(d?.id ? d : null)).catch(() => {});
    api.scenes().then(r => setAll(Array.isArray(r) ? r : r.items || [])).catch(() => {}); };
  useEffect(load, []); useLive(ev => { if (ev.event.startsWith('scene')) load(); });
  const s = day || all[0];
  return (
    <div className="wrap">
      <div className="kicker">scene of the day</div>
      <h1 className="page-title">{t('scene.day')}</h1>
      {!s && <p className="page-sub">Сцен пока нет. ИИ ждёт реплик в пуле.</p>}
      {s && (
        <div className="scene-stage fade-in">
          <div className="row-flex" style={{ justifyContent: 'space-between' }}>
            <span className="badge gold">#{s.id} · {t('scene.weight')} {Number(s.weight).toFixed(2)}</span>
            <span className="badge">{new Date(s.created_at).toLocaleDateString()}</span>
          </div>
          <div className="weight-bar"><i style={{ width: `${Math.min(100, Number(s.weight) * 100)}%` }} /></div>
          <div className="line-a">«{s.replica_a?.text}»</div>
          <hr className="hr" />
          <div className="line-b">«{s.replica_b?.text}»</div>
          {s.ai_comment && <p className="ai-comment">ИИ: {s.ai_comment}</p>}
          <div className="row-flex" style={{ justifyContent: 'center', color: 'var(--dim)', fontSize: 12 }}>
            <span>{s.replica_a?.display_name} ({s.replica_a?.step_level})</span><span>×</span><span>{s.replica_b?.display_name} ({s.replica_b?.step_level})</span>
          </div>
        </div>
      )}
      {all.length > 1 && <>
        <div className="spacer" /><div className="kicker">все сцены</div>
        <div className="grid grid-2">
          {all.slice(0, 12).map(x => (
            <div className="card" key={x.id}>
              <div className="mono" style={{ color: 'var(--accent)', fontSize: 13 }}>вес {Number(x.weight).toFixed(2)}</div>
              <p style={{ fontFamily: 'var(--serif)', fontSize: 16, marginTop: 8 }}>«{x.replica_a?.text?.slice(0, 90)}» ⟷ «{x.replica_b?.text?.slice(0, 90)}»</p>
            </div>
          ))}
        </div>
      </>}
    </div>
  );
}
