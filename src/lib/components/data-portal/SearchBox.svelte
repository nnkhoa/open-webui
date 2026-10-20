<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	import Icon from './Icon.svelte';

	export let value = '';
	export let placeholder = '';

	const dispatch = createEventDispatcher<{ search: string }>();

	let input = value;
	$: input = value;
</script>

<label class="srch">
	<Icon name="search" size={16} />
	<input
		class="inp"
		type="search"
		{placeholder}
		bind:value={input}
		on:keydown={(event) => {
			if (event.key === 'Enter') dispatch('search', input.trim());
		}}
	/>
</label>
