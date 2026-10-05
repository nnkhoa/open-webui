<script context="module" lang="ts">
	export type ExcelRow = { rowNumber: number; cells: (string | null)[]; hidden?: boolean };
</script>

<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let columns: string[] = [];
	export let rows: ExcelRow[] = [];
</script>

<div class="xl-wrap">
	<table class="xl">
		<thead>
			<tr>
				<th class="rn"></th>
				{#each columns as column}<th>{column}</th>{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as row}
				<tr
					class:hidden-row={row.hidden}
					title={row.hidden ? $i18n.t('Row is hidden in Excel (filter)') : undefined}
				>
					<td class="rn">{row.rowNumber}</td>
					{#each row.cells as value}<td title={value ?? ''}>{value ?? ''}</td>{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>
