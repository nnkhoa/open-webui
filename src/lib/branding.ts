// Logo khách lấy từ Project Config (Admin ▸ Project Config); chưa cấu hình thì dùng logo Open WebUI.
// Badge góc phải ghi nhận Open WebUI nên giữ cố định.
export const OPEN_WEBUI_LOGO_PATH = '/static/favicon.png';
export const OPEN_WEBUI_NAME = 'Open WebUI';

export const projectLogoSrc = (logoUrl: string | null | undefined, baseUrl: string): string =>
	`${baseUrl}${logoUrl || OPEN_WEBUI_LOGO_PATH}`;
