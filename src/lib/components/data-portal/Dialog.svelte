<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let wide = false;
	export let label = '';

	const dispatch = createEventDispatcher<{ close: void }>();

	const onKeydown = (event: KeyboardEvent) => {
		if (event.key === 'Escape') dispatch('close');
	};
</script>

<svelte:window on:keydown={onKeydown} />
<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="ov" on:click|self={() => dispatch('close')}>
	<div class="dlg" class:wide role="dialog" aria-modal="true" aria-label={label}>
		<slot />
	</div>
</div>
