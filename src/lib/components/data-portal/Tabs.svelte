<script context="module" lang="ts">
	export type Tab = { id: string; label: string; count?: string | number; hidden?: boolean };
</script>

<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let tabs: Tab[] = [];
	export let active = '';

	const dispatch = createEventDispatcher<{ change: string }>();
</script>

<section class="card">
	<div class="subtabs" role="tablist">
		{#each tabs as tab (tab.id)}
			<button
				type="button"
				role="tab"
				class="subtab"
				class:on={tab.id === active}
				aria-selected={tab.id === active}
				on:click={() => dispatch('change', tab.id)}
			>
				{tab.label}
				{#if tab.count !== undefined && tab.count !== ''}<span class="count">{tab.count}</span>{/if}
				{#if tab.hidden}<span class="hidden-tag">{$i18n.t('hidden')}</span>{/if}
			</button>
		{/each}
	</div>
	<slot />
</section>
