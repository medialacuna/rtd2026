import React, { createContext, useContext, useMemo } from 'react';

export type Lang = 'ru' | 'en';

const dict: Record<string, Record<Lang, string>> = {
  'nav.pool': { ru: 'Пул', en: 'Pool' },
  'nav.muar': { ru: 'Муар', en: 'Moiré' },
  'nav.scene': { ru: 'Сцена дня', en: 'Scene of the day' },
  'nav.acts': { ru: 'Акты', en: 'Acts' },
  'nav.plays': { ru: 'Пьесы · Комарово', en: 'Plays · Komarovo' },
  'nav.ai': { ru: 'Лог ИИ', en: 'AI log' },
  'nav.me': { ru: 'Я', en: 'Me' },
  'nav.stage': { ru: 'Сцена', en: 'Stage' },
  'tagline': { ru: 'Движок коллективной драматургии в реальном времени', en: 'Real-time collective dramaturgy engine' },
  'join.title': { ru: 'Вход по приглашению', en: 'Join by invitation' },
  'join.sub': { ru: 'Резиденция не заканчивается. Портал — нет.', en: 'The residency ends. The portal does not.' },
  'join.email': { ru: 'Email', en: 'Email' },
  'join.btn': { ru: 'Прислать ссылку', en: 'Send magic link' },
  'join.sent': { ru: 'Ссылка отправлена на почту. Проверь входящие.', en: 'Link sent. Check your inbox.' },
  'join.devlink': { ru: 'Dev-режим: ссылка не отправлена (SMTP не настроен). Открой:', en: 'Dev mode: no SMTP. Open:' },
  'pool.title': { ru: 'Пул реплик', en: 'Replica pool' },
  'pool.fresh': { ru: 'свежие', en: 'fresh' },
  'pool.resonant': { ru: 'резонансные', en: 'resonant' },
  'pool.contested': { ru: 'спорные', en: 'contested' },
  'pool.placeholder': { ru: 'Твоя реплика. До 280 знаков. Только своё.', en: 'Your line. Up to 280 chars. Only yours.' },
  'pool.send': { ru: 'В пул', en: 'To the pool' },
  'pool.tost': { ru: 'Тост такта', en: "Takt's toast" },
  'muar.title': { ru: 'Муар-карта', en: 'Moiré map' },
  'muar.sub': { ru: 'Две решётки накладываются — возникает узор, которого нет ни в одной.', en: 'Two grids overlap — a pattern appears that is in neither.' },
  'scene.day': { ru: 'Сцена дня', en: 'Scene of the day' },
  'scene.weight': { ru: 'вес муара', en: 'moiré weight' },
  'ai.witness': { ru: 'ИИ — свидетель, не автор', en: 'AI is a witness, not an author' },
  'plays.title': { ru: 'Библиотека пьес', en: 'Play library' },
  'plays.learned': { ru: 'ИИ усвоил', en: 'AI learned' },
  'fragments': { ru: 'фрагментов', en: 'fragments' },
  'maturity': { ru: 'Зрелость ИИ', en: 'AI maturity' },
  'stage.enter': { ru: 'Войти в Stage Mode', en: 'Enter Stage Mode' },
  'logout': { ru: 'Выйти', en: 'Logout' },
  'login': { ru: 'Войти', en: 'Login' },
};

interface I18nCtx { lang: Lang; t: (k: string) => string; setLang: (l: Lang) => void }
const Ctx = createContext<I18nCtx>({ lang: 'ru', t: (k) => k, setLang: () => {} });

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lg, setLg] = React.useState<Lang>(() => (localStorage.getItem('rtd-lang') as Lang) || 'ru');
  const value = useMemo<I18nCtx>(() => ({
    lang: lg,
    setLang: (l: Lang) => { localStorage.setItem('rtd-lang', l); setLg(l); document.documentElement.lang = l; },
    t: (k: string) => dict[k]?.[lg] ?? dict[k]?.ru ?? k,
  }), [lg]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
