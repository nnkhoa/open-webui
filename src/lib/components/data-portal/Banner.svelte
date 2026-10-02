<script lang="ts">
	import Icon from './Icon.svelte';
	export let k: 'ok' | 'err' | 'warn' | 'info' = 'info';
	export let icon = k === 'ok' ? 'check' : k === 'err' ? 'x' : k === 'warn' ? 'alert' : 'info';
	export let title: string;
	export let p = '';
	export let meta = '';
	export let big = false;
</script>

<div class="banner k-{k}" role={k === 'err' ? 'alert' : 'status'}>
	<Icon name={icon} size={24} stroke={1.7} className="i-{k}" />
	<div style="min-width:0">
		<div class="t" class:big>{title}</div>
		{#if p}<p>{p}</p>{/if}
		{#if meta}<div class="meta">{meta}</div>{/if}
		<slot />
	</div>
</div>
