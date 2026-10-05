<script context="module" lang="ts">
	export type ReadonlyField = { label: string; value: string | number | null; span?: number };
</script>

<script lang="ts">
	export let title: string;
	export let fields: ReadonlyField[] = [];
</script>

<section class="card">
	<div class="card-h">
		<div>
			<h2>{title}</h2>
		</div>
	</div>
	<div class="form-grid">
		{#each fields as field}
			<div class={field.span ? 's' + field.span : ''}>
				<span class="ro-l">{field.label}</span>
				<div class="ro">{field.value}</div>
			</div>
		{/each}
		<slot />
	</div>
</section>
