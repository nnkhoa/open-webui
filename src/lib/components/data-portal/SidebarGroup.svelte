<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { page } from '$app/stores';

	import { user } from '$lib/stores';
	import { DATA_PORTAL_ROLES, resetUploadDraft } from '$lib/stores/dataPortal';

	import Icon from './Icon.svelte';
	import './tokens.css';

	const i18n: Writable<i18nType> = getContext('i18n');

	const UPLOAD_PATH = '/data-portal/upload';
	const ITEMS = [
		{ href: UPLOAD_PATH, label: 'Upload data', icon: 'up', adminOnly: false },
		{ href: '/data-portal/history', label: 'Upload history', icon: 'list', adminOnly: false },
		{ href: '/data-portal/data', label: 'Data', icon: 'layers', adminOnly: false },
		{ href: '/data-portal/admin', label: 'Database configuration', icon: 'db', adminOnly: true }
	];

	export let onNavigate: () => void = () => {};

	let open = false;

	const toggle = () => {
		open = !open;
	};

	$: visible = DATA_PORTAL_ROLES.includes($user?.role ?? '');
	$: items = ITEMS.filter((item) => !item.adminOnly || $user?.role === 'admin');
	$: path = $page.url.pathname;
</script>

{#if visible}
	<div class="px-[0.4375rem] flex flex-col text-gray-800 dark:text-gray-200">
		<button
			type="button"
			class="grow flex items-center space-x-3 rounded-2xl px-2.5 py-2 hover:bg-gray-100 dark:hover:bg-gray-900 transition outline-none"
			aria-expanded={open}
			on:click={toggle}
		>
			<Icon name="db" size={18} />
			<span class="flex-1 text-left text-sm font-primary">{$i18n.t('Data Portal')}</span>
			<Icon name={open ? 'chevUp' : 'chev'} size={14} stroke={2.2} />
		</button>

		{#if open}
			<div class="dp-sub">
				{#each items as item (item.href)}
					{@const on = path === item.href || path.startsWith(item.href + '/')}
					<a
						href={item.href}
						class="dp-link {on ? 'on' : ''}"
						aria-current={on ? 'page' : undefined}
						draggable="false"
						on:click={() => {
							if (item.href === UPLOAD_PATH) resetUploadDraft();
							onNavigate();
						}}
					>
						<Icon name={item.icon} size={16} stroke={1.8} />
						<span>{$i18n.t(item.label)}</span>
					</a>
				{/each}
			</div>
		{/if}
	</div>
{/if}

<style>
	.dp-sub {
		display: flex;
		flex-direction: column;
		gap: 1px;
		margin: 2px 0 6px 19px;
		padding-left: 10px;
		border-left: 1px solid var(--line2);
	}
	.dp-link {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 7px 10px;
		border-radius: 12px;
		font-size: 14px;
		color: var(--text);
		transition: background 0.12s;
	}
	.dp-link:hover {
		background: var(--hover);
	}
	.dp-link.on {
		background: var(--hover);
		color: var(--strong);
		font-weight: 500;
	}
</style>
