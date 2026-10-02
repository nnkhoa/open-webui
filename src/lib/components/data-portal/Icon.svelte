<script lang="ts">
	import { ICON } from './icons';
	export let name: string;
	export let size = 18;
	export let stroke = 2;
	export let className = '';
</script>

<svg
	class={className}
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width={stroke}
	aria-hidden="true"
	style="flex-shrink:0"
	><path stroke-linecap="round" stroke-linejoin="round" d={ICON[name]} /></svg
>
