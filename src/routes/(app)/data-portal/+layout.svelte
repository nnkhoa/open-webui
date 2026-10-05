<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { toast } from 'svelte-sonner';

	import { user, showSidebar, mobile, WEBUI_NAME } from '$lib/stores';
	import { DATA_PORTAL_ROLES } from '$lib/stores/dataPortal';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import '$lib/components/data-portal/tokens.css';
	import '$lib/components/data-portal/dp.css';

	const i18n: Writable<i18nType> = getContext('i18n');

	const ADMIN_PATH = '/data-portal/admin';
	const SECTIONS = [
		{ href: '/data-portal/upload', label: 'Upload data' },
		{ href: '/data-portal/history', label: 'Upload history' },
		{ href: '/data-portal/data', label: 'Data' },
		{ href: ADMIN_PATH, label: 'Database configuration' }
	];

	let warned = false;

	$: path = $page.url.pathname;
	$: role = $user?.role ?? '';
	$: allowed =
		DATA_PORTAL_ROLES.includes(role) && (role === 'admin' || !path.startsWith(ADMIN_PATH));
	$: section =
		SECTIONS.find(({ href }) => path === href || path.startsWith(href + '/'))?.label ?? '';

	$: if ($user && !DATA_PORTAL_ROLES.includes(role)) {
		if (!warned) {
			warned = true;
			toast.error(
				$i18n.t(
					'You do not have permission to access Data Portal. Contact Admin if you need to upload data.'
				)
			);
		}
		goto('/');
	} else if ($user && role !== 'admin' && path.startsWith(ADMIN_PATH)) {
		goto('/data-portal/upload');
	}
</script>

<svelte:head>
	<title>{$i18n.t('Data Portal')} • {$WEBUI_NAME}</title>
</svelte:head>

{#if allowed}
	<div
		class="dp flex flex-col w-full h-full max-h-full transition-width duration-200 ease-in-out {$showSidebar
			? 'md:max-w-[calc(100%-var(--sidebar-width))]'
			: ''} max-w-full"
	>
		<header class="dp-topbar">
			{#if !$showSidebar || $mobile}
				<Tooltip content={$i18n.t('Open Sidebar')} interactive={true}>
					<button
						type="button"
						class="dp-icon-btn"
						aria-label={$i18n.t('Open Sidebar')}
						on:click={() => showSidebar.set(!$showSidebar)}
					>
						<SidebarIcon />
					</button>
				</Tooltip>
			{/if}
			<nav class="dp-crumb" aria-label={$i18n.t('Data Portal')}>
				<span>{$i18n.t('Data Portal')}</span>
				<Icon name="fwd" size={14} />
				<b>{section ? $i18n.t(section) : ''}</b>
			</nav>
		</header>
		<main class="dp-main">
			<slot />
		</main>
	</div>
{/if}
