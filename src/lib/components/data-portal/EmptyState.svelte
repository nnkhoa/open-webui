<script lang="ts">
	// Trạng thái trống (đặc tả 12.16).
	import Icon from './Icon.svelte';
	export let icon = 'info';
	export let title: string;
	export let p = '';
</script>

<div class="empty">
	<div class="o"><Icon name={icon} size={26} stroke={1.7} /></div>
	<h2>{title}</h2>
	{#if p}<p>{p}</p>{/if}
	<slot />
</div>
