import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { useI18n } from '../i18n/i18n';

export default function Acts() {
  const { t } = useI18n();
  const [acts, setActs] = useState<any[]>([]); const [open, setOpen] = useState<any>(null);
  useEffect(() => { api.acts().then(r => setActs(Array.isArray(r) ? r : [])).catch(() => {}); }, []);
  return (
    <div className="wrap">
      <div className="kicker">week → act → play</div>
      <h1 className="page-title">{t('nav.acts')}</h1>
      {acts.length === 0 && <p className="page-sub">Акты собираются из лучших сцен недели. Пока собрано ничего нет — играйте.</p>}
      <div className="grid grid-2" style={{ marginTop: 24 }}>
        {acts.map(a => (
          <div className="card" key={a.id}>
            <div className="kicker">{a.theme || 'act'}</div>
            <h3 style={{ fontFamily: 'var(--display)', fontWeight: 600 }}>{a.title}</h3>
            <p style={{ color: 'var(--dim)', fontSize: 13, margin: '8px 0 14px' }}>{a.scenes_count ?? a.scene_ids?.length ?? 0} сцен · {new Date(a.created_at).toLocaleDateString()}</p>
            <button className="btn ghost" onClick={() => api.act(a.id).then(setOpen)}>Читать →</button>
          </div>
        ))}
      </div>
      {open && (
        <div className="modal" onClick={() => setOpen(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.7)', zIndex: 60, display: 'grid', placeItems: 'center', padding: 20 }}>
          <div className="card" style={{ maxWidth: 760, width: '100%', maxHeight: '80vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ fontFamily: 'var(--display)' }}>{open.title}</h3>
            {(open.scenes || []).map((s: any) => (
              <div key={s.id} style={{ margin: '18px 0' }}>
                <p className="line-a" style={{ fontSize: 18 }}>«{s.replica_a?.text}»</p>
                <p className="line-b" style={{ fontSize: 18 }}>«{s.replica_b?.text}»</p>
                {s.ai_comment && <p className="ai-comment">ИИ: {s.ai_comment}</p>}
              </div>
            ))}
            <button className="btn ghost" onClick={() => setOpen(null)}>Закрыть</button>
          </div>
        </div>
      )}
    </div>
  );
}
