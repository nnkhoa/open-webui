import i18next from 'i18next';
import type { i18n as i18nType } from 'i18next';
import { writable } from 'svelte/store';

export const PORTAL_LOCALE = 'vi-VN';

const portalTranslator = () => ({ t: i18next.getFixedT(PORTAL_LOCALE) }) as unknown as i18nType;

const portalI18n = writable<i18nType>(portalTranslator());

let loading: Promise<void> | null = null;

export const loadPortalLocale = () => {
	loading ??= i18next.loadLanguages(PORTAL_LOCALE).then(() => portalI18n.set(portalTranslator()));
	return loading;
};

export default portalI18n;
