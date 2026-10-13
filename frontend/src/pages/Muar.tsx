import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { useI18n } from '../i18n/i18n';

export default function Muar() {
  const { t } = useI18n();
  const [map, setMap] = useState<any>({ nodes: [], edges: [] });
  useEffect(() => { api.muarMap().then(setMap).catch(() => {}); }, []);
  const nodes: any[] = map.nodes || []; const edges: any[] = map.edges || [];
  const W = 900, H = 560;
  const pos = new Map<number, { x: number; y: number }>();
  nodes.forEach((n, i) => {
    const a = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
    const r = 170 + (i % 3) * 60;
    pos.set(n.id, { x: W / 2 + Math.cos(a) * r * 1.4, y: H / 2 + Math.sin(a) * r });
  });
  return (
    <div className="wrap">
      <div className="kicker">Module 5 · resonance engine</div>
      <h1 className="page-title">{t('muar.title')}</h1>
      <p className="page-sub">{t('muar.sub')}</p>
      <div className="spacer" />
      <div className="map-frame fade-in">
        <svg viewBox={`0 0 ${W} ${H}`}>
          {edges.map((e, i) => {
            const a = pos.get(e.a), b = pos.get(e.b); if (!a || !b) return null;
            const conflict = e.kind === 'conflict';
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={conflict ? '#d9b36c' : '#7ee0c3'} strokeWidth={Math.max(1, (e.weight || .5) * 4)}
              strokeOpacity={.55} strokeDasharray={conflict ? '6 4' : ''} />;
          })}
          {nodes.map(n => { const p = pos.get(n.id)!;
            return <g key={n.id}>
              <circle cx={p.x} cy={p.y} r={10 + Math.min(14, (n.count || 1) * 3)} fill="#111114" stroke="#d9b36c" strokeOpacity=".7" />
              <text x={p.x} y={p.y - 20} textAnchor="middle" fill="#8f8d86" fontSize="12" fontFamily="Manrope">{n.label}</text>
              <text x={p.x} y={p.y + 4} textAnchor="middle" fill="#f2f0ea" fontSize="13" fontFamily="Unbounded">{n.count || 1}</text>
            </g>; })}
        </svg>
      </div>
      <div className="legend">
        <span><i style={{ background: '#7ee0c3' }} />резонанс / resonance</span>
        <span><i style={{ background: '#d9b36c' }} />муар / конфликт / moiré</span>
        <span>узлы — участники · линии — сцены</span>
      </div>
    </div>
  );
}
