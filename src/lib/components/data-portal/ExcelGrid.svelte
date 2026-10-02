<script lang="ts">
	// Lưới kiểu Excel (đặc tả 12.14).
	export let cols: string[] = []; // A, B, C…
	export let rows: { rn: number; cells: (string | null)[]; an?: boolean }[] = [];
</script>

<div class="xl-wrap">
	<table class="xl">
		<thead>
			<tr>
				<th class="rn"></th>
				{#each cols as c}<th>{c}</th>{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as r}
				<tr class:an={r.an} title={r.an ? 'Dòng đang bị ẩn trong Excel (bộ lọc)' : undefined}>
					<td class="rn">{r.rn}</td>
					{#each r.cells as v}<td title={v ?? ''}>{v ?? ''}</td>{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>
