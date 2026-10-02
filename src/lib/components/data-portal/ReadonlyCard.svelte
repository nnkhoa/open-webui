<script lang="ts">
	// Thẻ thông tin chỉ đọc (đặc tả 12.5).
	export let title: string;
	export let sub = '';
	export let fields: { l: string; v: string | number; span?: number }[] = [];
</script>

<section class="card">
	<div class="card-h">
		<div>
			<h2>{title}</h2>
			{#if sub}<div class="sub">{sub}</div>{/if}
		</div>
	</div>
	<div class="form-grid">
		{#each fields as f}
			<div class={f.span ? 's' + f.span : ''}>
				<span class="ro-l">{f.l}</span>
				<div class="ro">{f.v}</div>
			</div>
		{/each}
		<slot />
	</div>
</section>
