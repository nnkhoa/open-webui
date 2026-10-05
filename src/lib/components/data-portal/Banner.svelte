<script lang="ts">
	import Icon from './Icon.svelte';

	export let tone: 'ok' | 'err' | 'warn' | 'info' = 'info';
	export let icon =
		tone === 'ok' ? 'check' : tone === 'err' ? 'x' : tone === 'warn' ? 'alert' : 'info';
	export let title: string;
	export let description = '';
	export let big = false;
</script>

<div class="banner k-{tone}" role={tone === 'err' ? 'alert' : 'status'}>
	<Icon name={icon} size={24} stroke={1.7} className="i-{tone}" />
	<div style="min-width:0">
		<div class="t" class:big>{title}</div>
		{#if description}<p>{description}</p>{/if}
		<slot />
	</div>
</div>
