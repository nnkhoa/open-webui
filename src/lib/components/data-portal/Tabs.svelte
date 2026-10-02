<script lang="ts">
	// Tab trong màn (đặc tả 12.12).
	import { createEventDispatcher } from 'svelte';
	export let tabs: { id: string; t: string; n?: string | number; an?: boolean }[] = [];
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
				{tab.t}
				{#if tab.n !== undefined && tab.n !== ''}<span class="count">{tab.n}</span>{/if}
				{#if tab.an}<span class="an-tag">ẩn</span>{/if}
			</button>
		{/each}
	</div>
	<slot />
</section>
