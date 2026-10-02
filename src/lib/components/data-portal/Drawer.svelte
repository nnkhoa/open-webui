<script lang="ts">
	// Ngăn trượt từ phải (đặc tả 12.13).
	import { createEventDispatcher } from 'svelte';
	export let label = '';
	const dispatch = createEventDispatcher<{ close: void }>();
</script>

<svelte:window on:keydown={(e) => e.key === 'Escape' && dispatch('close')} />
<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="ov right" on:click|self={() => dispatch('close')}>
	<aside class="drawer" role="dialog" aria-modal="true" aria-label={label}>
		<slot />
	</aside>
</div>
