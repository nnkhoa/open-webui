<script lang="ts">
	import Icon from './Icon.svelte';

	export let label: string;
	export let value: string;
</script>

<span class="dropdown-pill chip locked"
	><Icon name="lock" size={13} /><span class="k">{label}:</span><span class="nm">{value}</span
	></span
>
