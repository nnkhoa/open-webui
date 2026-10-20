import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { OPEN_WEBUI_LOGO_PATH, OPEN_WEBUI_NAME, projectLogoSrc } from './branding';

// Thư mục `static/` ở gốc repo được phục vụ ở `/`.
const staticFile = (urlPath: string) =>
	fileURLToPath(new URL(`../../static${urlPath}`, import.meta.url));

describe('projectLogoSrc', () => {
	it('dùng logo trong Project Config khi đã cấu hình', () => {
		expect(projectLogoSrc('/api/v1/files/project_logo/abc.png', 'http://host')).toBe(
			'http://host/api/v1/files/project_logo/abc.png'
		);
		expect(projectLogoSrc('/static/fpt-logo.webp', '')).toBe('/static/fpt-logo.webp');
	});

	it.each([null, undefined, ''])('chưa cấu hình (%s) thì về logo Open WebUI', (logoUrl) => {
		expect(projectLogoSrc(logoUrl, 'http://host')).toBe(`http://host${OPEN_WEBUI_LOGO_PATH}`);
	});
});

describe('Open WebUI badge', () => {
	it('logo có tệp trong static/', () => {
		expect(existsSync(staticFile(OPEN_WEBUI_LOGO_PATH))).toBe(true);
	});

	it('giữ đúng tên hiển thị', () => {
		expect(OPEN_WEBUI_NAME).toBe('Open WebUI');
	});
});
