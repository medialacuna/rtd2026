import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useLive } from '../hooks/useLive';

const SECTIONS: Record<string, string> = { lestnica: 'ЛЕСТНИЦА', genesis: 'ГЕНЕЗИС', theories: 'ТЕОРИИ', muar: 'МУАР' };

function NeuralCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current!; const ctx = cv.getContext('2d')!; let raf = 0; let t = 0;
    const pts = Array.from({ length: 46 }, () => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - .5) * .0016, vy: (Math.random() - .5) * .0016 }));
    const draw = () => {
      const w = cv.width = cv.offsetWidth, h = cv.height = cv.offsetHeight; ctx.clearRect(0, 0, w, h); t += .01;
      pts.forEach(p => { p.x += p.vx; p.y += p.vy; if (p.x < 0 || p.x > 1) p.vx *= -1; if (p.y < 0 || p.y > 1) p.vy *= -1; });
      for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
        const dx = (pts[i].x - pts[j].x) * w, dy = (pts[i].y - pts[j].y) * h, d = Math.hypot(dx, dy);
        if (d < w * .18) { ctx.strokeStyle = `rgba(217,179,108,${(1 - d / (w * .18)) * .25})`; ctx.beginPath(); ctx.moveTo(pts[i].x * w, pts[i].y * h); ctx.lineTo(pts[j].x * w, pts[j].y * h); ctx.stroke(); }
      }
      pts.forEach((p, i) => { const r = 2 + Math.sin(t + i) * 1.2; ctx.fillStyle = 'rgba(126,224,195,.8)'; ctx.beginPath(); ctx.arc(p.x * w, p.y * h, r, 0, 7); ctx.fill(); });
      raf = requestAnimationFrame(draw);
    };
    draw(); return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={ref} className="neural" style={{ width: '100%', height: '100%' }} />;
}

export default function Stage() {
  const [state, setState] = useState<any>(null); const [prompt, setPrompt] = useState(''); const [answer, setAnswer] = useState(''); const [busy, setBusy] = useState(false);
  const load = () => api.stageState().then(setState).catch(e => setState({ error: e.message }));
  useEffect(() => { load(); }, []);
  useLive(ev => { if (ev.event === 'stage:event') load(); });
  const next = async () => { try { await api.stageNext(); } catch (e: any) { alert(e.message); } load(); };
  const start = async () => { try { await api.stageStart('rtd-live-' + Date.now()); } catch (e: any) { alert(e.message); } load(); };
  const ask = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true);
    try { const r = await api.stageAsk(prompt || 'Приведи зрителя сюда.'); setAnswer(r.answer || JSON.stringify(r)); } catch (er: any) { setAnswer(er.message); } finally { setBusy(false); } };
  const sec = state?.current_section || state?.section;
  return (
    <div className="stage-mode wrap">
      <NeuralCanvas />
      <div style={{ position: 'relative', zIndex: 2, width: '100%' }}>
        <div className="kicker pulse">STAGE MODE · rtd.heartwins.ru</div>
        {state?.error && <h2 className="section-orb" style={{ fontSize: 26 }}>{state.error}</h2>}
        {state?.locked && <button className="btn" onClick={start}>Активировать сеанс</button>}
        {sec && <>
          <h1 className="section-orb">{SECTIONS[String(sec).toLowerCase()] || sec}</h1>
          <p className="stage-answer">{state.subtitle || state.guide_line || 'ИИ ведёт зрителя.'}</p>
          <div className="row-flex" style={{ justifyContent: 'center' }}>
            <button className="btn ghost" onClick={next}>Дальше →</button>
            <span className="badge">maturity {state.maturity_score ?? '—'}</span>
            <span className="badge green">зал: {state.online ?? 0}</span>
          </div>
          <form onSubmit={ask} className="join-card" style={{ marginTop: 30 }}>
            <div className="field"><input value={prompt} placeholder="Реплика актёра или вопрос зала…" onChange={e => setPrompt(e.target.value)} /></div>
            <div className="spacer" /><button className="btn" disabled={busy}>{busy ? '…' : 'Спросить ИИ'}</button>
            {answer && <p className="stage-answer" style={{ color: 'var(--accent2)' }}>{answer}</p>}
          </form>
        </>}
      </div>
    </div>
  );
}
