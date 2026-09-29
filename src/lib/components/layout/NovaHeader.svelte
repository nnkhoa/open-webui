<script lang="ts">
	import { getContext, createEventDispatcher } from 'svelte';
	import { user, showSettings } from '$lib/stores';
	import { projectConfig } from '$lib/stores/projectConfig';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import UserMenu from '$lib/components/layout/Sidebar/UserMenu.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	$: orgName = $projectConfig.org_name || 'Nova Consumer Group';
	$: orgSubtitle = $projectConfig.org_subtitle || 'Chương trình tư vấn chiến lược AI';
	$: orgNameColor = $projectConfig.brand_color || '#86c52e';
	$: customLogoSrc = $projectConfig.logo_url
		? `${WEBUI_BASE_URL}${$projectConfig.logo_url}`
		: '/static/logoCustomer.png';
	$: orgSubtitleColor = '#555555';

	$: userInitial = (() => {
		const name = ($user?.name ?? $user?.email ?? '').trim();
		if (!name) return 'U';
		const parts = name.split(/\s+/);
		return (
			parts
				.slice(0, 2)
				.map((p) => p.charAt(0).toUpperCase())
				.join('') || 'U'
		);
	})();

	export let unreadCount = 0;
	export let onMobileMenuToggle: (() => void) | undefined = undefined;
</script>

<header
	class="nova-header fixed top-0 left-0 right-0 z-50 flex items-center justify-between overflow-hidden bg-white md:bg-transparent"
	style="height: var(--topbar-height, 56px);"
>
	<!-- Mobile header -->
	<div class="flex md:hidden items-center justify-between w-full h-full bg-white px-4">
		<div class="flex items-center gap-3">
			<div class="shrink-0">
				<img
					src={customLogoSrc}
					alt="Customer Logo"
					class="object-contain"
					style="width: 50px; height: 40px;"
					draggable="false"
					on:error={(e) => {
						e.currentTarget.src = '/static/logoCustomer.png';
					}}
				/>
			</div>
			{#if onMobileMenuToggle}
				<button
					type="button"
					on:click={onMobileMenuToggle}
					class="w-10 h-10 mt-1 flex items-center justify-center rounded-lg hover:bg-[#F3F4F6] transition-colors cursor-pointer"
					aria-label="Menu"
				>
					<svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
						<path
							d="M3 5.5h16M3 11h16M3 16.5h16"
							stroke="#444"
							stroke-width="1.8"
							stroke-linecap="round"
						/>
					</svg>
				</button>
			{/if}
		</div>
		<button
			type="button"
			class="h-10 w-10 rounded-full flex items-center justify-center shadow-sm overflow-hidden shrink-0 cursor-pointer"
			style="background: linear-gradient(to bottom, #1966B9, #0954A4);"
			aria-label={$i18n.t('User menu')}
			on:click={() => dispatch('user')}
		>
			{#if $user?.profile_image_url}
				<img
					src={$user.profile_image_url}
					alt=""
					class="w-full h-full object-cover"
					draggable="false"
				/>
			{:else}
				<span class="text-white text-sm font-bold leading-none">{userInitial}</span>
			{/if}
		</button>
	</div>

	<!-- Desktop left (white bg) -->
	<div class="hidden md:flex h-full bg-white items-center pl-7 gap-5 flex-1 min-w-0">
		<div class="shrink-0">
			<img
				src={customLogoSrc}
				alt="Customer Logo"
				class="object-contain"
				style="width: 60px; height: 40px;"
				draggable="false"
				on:error={(e) => {
					e.currentTarget.src = '/static/logoCustomer.png';
				}}
			/>
		</div>

		<div class="leading-[1.2]">
			<div
				class="text-[22px] tracking-[-0.15px] font-semibold"
				style="color: {orgNameColor};"
			>
				{orgName}
			</div>
			<div class="text-[13px] tracking-[-0.15px]" style="color: {orgSubtitleColor};">
				{orgSubtitle}
			</div>
		</div>
	</div>

	<!-- Desktop right (dark blue bg) -->
	<div class="hidden md:flex items-center h-full" style="background: #063374;">
		<!-- Diagonal banner transition -->
		<div class="flex h-full items-center -mr-px">
			<img
				src="/static/BannerHeader.svg"
				alt=""
				class="h-full w-auto block"
				draggable="false"
				aria-hidden="true"
			/>
		</div>

		<div class="flex" style="gap: 80px;">
			<!-- "Thực hiện bởi" + FPT Digital -->
			<div class="flex items-center gap-2 mr-2">
				<span
					class="text-[12px] font-normal whitespace-nowrap"
					style="color: #D2E3FA;"
				>
					Thực hiện bởi
				</span>
				<img
					src="/static/fpt-digital.svg"
					alt="FPT Digital"
					class="block"
					style="width: 80px; height: 30px;"
					draggable="false"
				/>
			</div>

			<!-- Action buttons -->
			<div class="flex items-center gap-2 pr-4">
				<!-- Settings (admin only) -->
				{#if $user?.role === 'admin'}
					<button
						type="button"
						aria-label={$i18n.t('Settings')}
						title={$i18n.t('Settings')}
						class="flex w-10 h-10 rounded-full items-center justify-center transition-colors cursor-pointer header-icon-btn"
						on:click={() => {
							showSettings.set(true);
							dispatch('settings');
						}}
					>
						<svg
							width="16"
							height="16"
							viewBox="0 0 16 16"
							fill="none"
							xmlns="http://www.w3.org/2000/svg"
							aria-hidden="true"
						>
							<path
								d="M10.0625 0H5.93682L5.46354 2.35418C5.07168 2.52877 4.69907 2.74325 4.35167 2.99418L2.06209 2.224L0 5.776L1.81484 7.36145C1.77101 7.78604 1.77101 8.21396 1.81484 8.63855L0 10.224L2.06282 13.776L4.35167 13.0065C4.69693 13.2553 5.06853 13.4705 5.46354 13.6458L5.93682 16H10.0625L10.5357 13.6458C10.9276 13.4712 11.3002 13.2568 11.6476 13.0058L13.9372 13.776L16 10.224L14.1844 8.63855C14.2283 8.21396 14.2283 7.78604 14.1844 7.36145L15.9993 5.776L13.9365 2.224L11.6483 2.99345C11.3009 2.74277 10.9283 2.52854 10.5365 2.35418L10.0625 0ZM7.99963 10.9091C7.22362 10.9091 6.47938 10.6026 5.93065 10.057C5.38192 9.51148 5.07365 8.77154 5.07365 8C5.07365 7.22846 5.38192 6.48852 5.93065 5.94296C6.47938 5.3974 7.22362 5.09091 7.99963 5.09091C8.77565 5.09091 9.51989 5.3974 10.0686 5.94296C10.6173 6.48852 10.9256 7.22846 10.9256 8C10.9256 8.77154 10.6173 9.51148 10.0686 10.057C9.51989 10.6026 8.77565 10.9091 7.99963 10.9091Z"
								fill="white"
							/>
						</svg>
					</button>
				{/if}

				<!-- User avatar: admin = full menu, user = Sign Out only -->
				<UserMenu
					role={$user?.role}
					minimal={$user?.role !== 'admin'}
					help={$user?.role === 'admin'}
					showActiveUsers={false}
				>
					<button
						type="button"
						aria-label={$i18n.t('User menu')}
						title={$user?.name ?? $i18n.t('Profile')}
						class="h-9 w-9 rounded-full flex items-center justify-center shadow-sm overflow-hidden shrink-0 cursor-pointer"
						style="background: linear-gradient(to bottom, #1966B9, #0954A4);"
					>
						{#if $user?.profile_image_url}
							<img
								src={$user.profile_image_url}
								alt=""
								class="w-full h-full object-cover"
								draggable="false"
							/>
						{:else}
							<span class="text-white text-xs font-bold leading-none">{userInitial}</span>
						{/if}
					</button>
				</UserMenu>
			</div>
		</div>
	</div>
</header>

<style>
	.header-icon-btn {
		background: #0c3c82;
		border: none;
		color: #fff;
	}
	.header-icon-btn:hover {
		background: #2560b8;
	}
</style>
