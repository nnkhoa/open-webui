<script lang="ts">
	// Ô Tìm ở hàng lọc: Enter để tìm (đặc tả 12.4).
	import { createEventDispatcher } from 'svelte';
	import Icon from './Icon.svelte';
	export let value = '';
	export let placeholder = '';
	const dispatch = createEventDispatcher<{ search: string }>();
	let nhap = value;
	$: nhap = value;
</script>

<label class="srch">
	<Icon name="search" size={16} />
	<input
		class="inp"
		type="search"
		{placeholder}
		bind:value={nhap}
		on:keydown={(e) => {
			if (e.key === 'Enter') dispatch('search', nhap.trim());
		}}
	/>
</label>
