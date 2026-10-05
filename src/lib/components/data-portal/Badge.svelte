<script lang="ts">
	import type { Tone } from './format';

	export let label: string;
	export let tone: Tone | string = 'muted';
</script>

<span class="badge b-{tone}">{label}</span>
