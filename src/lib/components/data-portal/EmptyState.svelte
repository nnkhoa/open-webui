<script lang="ts">
	import Icon from './Icon.svelte';

	export let icon = 'info';
	export let title: string;
	export let description = '';
</script>

<div class="empty">
	<div class="o"><Icon name={icon} size={26} stroke={1.7} /></div>
	<h2>{title}</h2>
	{#if description}<p>{description}</p>{/if}
	<slot />
</div>
