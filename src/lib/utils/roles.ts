import { ADMIN_ROLE, DATA_UPLOADER_ROLE, USER_ROLE } from '$lib/constants';

const ROLE_BADGE_TYPES = new Map([
	[ADMIN_ROLE, 'info'],
	[USER_ROLE, 'success'],
	[DATA_UPLOADER_ROLE, 'warning']
]);

export const getRoleBadgeType = (role: string) => ROLE_BADGE_TYPES.get(role) ?? 'muted';
