<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Icon from './Icon.svelte';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let title: string;
	export let description = '';
	export let back: (() => void) | null = null;
</script>

<section class="card hcard">
	<div class="l">
		{#if back}
			<button
				type="button"
				class="back"
				aria-label={$i18n.t('Go back')}
				title={$i18n.t('Go back')}
				on:click={back}
			>
				<Icon name="arrowL" size={20} />
			</button>
		{/if}
		<div style="min-width:0">
			<h1>{title}<slot name="after" /></h1>
			{#if description}<p class="desc">{description}</p>{/if}
		</div>
	</div>
	{#if $$slots.actions}<div class="row"><slot name="actions" /></div>{/if}
</section>
