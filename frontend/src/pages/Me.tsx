import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../hooks/useAuth';

export default function Me() {
  const { user, logout, refresh } = useAuth(); const nav = useNavigate();
  const [steps, setSteps] = useState<any[]>([]);
  useEffect(() => { if (!user) nav('/'); api.steps().then(setSteps).catch(() => {}); }, [user]);
  if (!user) return null;
  const changeStep = async (level: string) => { try { await api.patchMe({ step_level: level }); refresh(); } catch (e: any) { alert(e.message); } };
  return (
    <div className="wrap">
      <div className="kicker">profile · права · ступень</div>
      <h1 className="page-title">{user.display_name || user.email}</h1>
      <div className="grid grid-2" style={{ marginTop: 26 }}>
        <div className="card">
          <div className="kicker">твоя оптика (менять — раз в сутки)</div>
          {steps.map(s => (
            <button key={s.level} className="btn ghost" style={{ margin: '6px 6px 0 0', padding: '8px 16px', fontSize: 13,
              borderColor: user.step_level === s.level ? 'var(--accent)' : undefined }}
              onClick={() => changeStep(s.level)}>{s.level} · {s.function}</button>
          ))}
        </div>
        <div className="card">
          <div className="kicker">права</div>
          <p style={{ fontSize: 14, color: 'var(--dim)' }}>Реплика — объект твоего авторского права. Портал имеет лицензию на использование внутри игры. При постановке сцены роялти делится поровну между авторами реплик. Отозвать реплику можно — сцена перепишется без неё.</p>
          <div className="spacer" />
          <div className="row-flex"><span className="badge gold">токены: {user.tokens_balance}</span><span className="badge">роль: {user.role}</span></div>
          <div className="spacer" /><button className="btn ghost" onClick={() => { logout(); nav('/'); }}>Выйти</button>
        </div>
      </div>
    </div>
  );
}
