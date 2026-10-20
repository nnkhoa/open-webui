<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Icon from './Icon.svelte';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let title: string;
	export let open = false;
</script>

<button type="button" class="card xp" aria-expanded={open} on:click={() => (open = !open)}>
	<span class="xp-t"><b>{title}</b></span>
	<span class="xp-r"
		>{open ? $i18n.t('Collapse') : $i18n.t('View details')}<Icon
			name={open ? 'chevUp' : 'chev'}
			size={16}
			stroke={2.2}
		/></span
	>
</button>
{#if open}<slot />{/if}
