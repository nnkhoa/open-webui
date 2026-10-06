import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

// Menu user ở chân sidebar là lối vào Settings duy nhất từ khi bỏ NovaHeader (2fc03fa20).
const source = readFileSync(fileURLToPath(new URL('./UserMenu.svelte', import.meta.url)), 'utf8');

describe('UserMenu', () => {
	it('có mục mở Settings', () => {
		expect(source).toContain('showSettings.set(true)');
		expect(source).toContain("$i18n.t('Settings')");
	});
});
