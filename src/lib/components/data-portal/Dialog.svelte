<script lang="ts">
	// Hộp thoại (đặc tả 12.13). Bấm ra ngoài hoặc Esc thì đóng.
	import { createEventDispatcher } from 'svelte';
	export let wide = false;
	export let label = '';
	const dispatch = createEventDispatcher<{ close: void }>();
	const phim = (e: KeyboardEvent) => {
		if (e.key === 'Escape') dispatch('close');
	};
</script>

<svelte:window on:keydown={phim} />
<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="ov" on:click|self={() => dispatch('close')}>
	<div class="dlg" class:wide role="dialog" aria-modal="true" aria-label={label}>
		<slot />
	</div>
</div>
