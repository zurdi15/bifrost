import { createI18n } from 'vue-i18n';

import en from './en.json';
import es from './es.json';

export const i18n = createI18n({
  legacy: false,
  locale: navigator.language.startsWith('es') ? 'es' : 'en',
  fallbackLocale: 'en',
  messages: { en, es },
});
