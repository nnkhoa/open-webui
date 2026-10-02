<script lang="ts">
	// Nhóm "Data Portal" trên thanh bên Open WebUI (đặc tả 14.1). Chỉ Admin và Data Loader thấy.
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import { user } from '$lib/stores';
	import { DP_ROLES, dpNap, NAP_TRONG } from '$lib/stores/dataPortal';
	import Icon from './Icon.svelte';
	import './tokens.css';

	const i18n = getContext('i18n');

	export let onNavigate: () => void = () => {};

	const MUC = [
		{ href: '/data-portal/upload', label: 'Upload data', icon: 'up', adminOnly: false },
		{ href: '/data-portal/history', label: 'Upload history', icon: 'list', adminOnly: false },
		{ href: '/data-portal/data', label: 'Data', icon: 'layers', adminOnly: false },
		{ href: '/data-portal/admin', label: 'Database configuration', icon: 'db', adminOnly: true }
	];

	// Mặc định đóng; bấm dòng "Data Portal" mới hiện các mục con.
	let open = false;
	const toggle = () => {
		open = !open;
	};

	$: visible = DP_ROLES.includes($user?.role ?? '');
	$: items = MUC.filter((m) => !m.adminOnly || $user?.role === 'admin');
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
				{#each items as m (m.href)}
					{@const on = path === m.href || path.startsWith(m.href + '/')}
					<a
						href={m.href}
						class="dp-link {on ? 'on' : ''}"
						aria-current={on ? 'page' : undefined}
						draggable="false"
						on:click={() => {
							// Mỗi lần mở mục Nạp dữ liệu, mọi ô trở lại trống (đặc tả 15.1).
							if (m.href === '/data-portal/upload') dpNap.set({ ...NAP_TRONG });
							onNavigate();
						}}
					>
						<Icon name={m.icon} size={16} stroke={1.8} />
						<span>{$i18n.t(m.label)}</span>
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
