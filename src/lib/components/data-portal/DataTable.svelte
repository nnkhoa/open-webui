<script context="module" lang="ts">
	export type TableCellObject = {
		value?: string | number | null;
		subtitle?: string;
		badge?: { label: string; tone: string };
		action?: () => void;
		actionTitle?: string;
		className?: string;
		bold?: boolean;
		file?: boolean;
	};
	export type TableCell = string | number | null | undefined | TableCellObject;
	export type TableRow = { cells: TableCell[]; onClick?: () => void; title?: string };
	export type TableHeader = { label: string; alignRight?: boolean; title?: string };
</script>

<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Badge from './Badge.svelte';
	import Icon from './Icon.svelte';
	import { isBlank } from './format';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let headers: TableHeader[] = [];
	export let rows: TableRow[] = [];
	export let totals: TableCell[] | null = null;

	const toObject = (cell: TableCell): TableCellObject =>
		cell !== null && typeof cell === 'object' ? cell : { value: cell };
	const display = (value: unknown) => (isBlank(value) ? '—' : String(value));
</script>

<div class="tw">
	<div class="tbox">
		<table>
			<thead>
				<tr>
					{#each headers as header}<th class:r={header.alignRight} title={header.title}
							>{header.label}</th
						>{/each}
				</tr>
			</thead>
			<tbody>
				{#each rows as row}
					<tr
						class:rc={!!row.onClick}
						tabindex={row.onClick ? 0 : undefined}
						title={row.onClick ? row.title || $i18n.t('Click to open') : undefined}
						on:click={row.onClick}
						on:keydown={(event) => {
							if (row.onClick && event.key === 'Enter') row.onClick();
						}}
					>
						{#each row.cells as rawCell, index}
							{@const cell = toObject(rawCell)}
							<td
								class="{headers[index]?.alignRight ? 'r ' : ''}{cell.className ?? ''}"
								class:muted={isBlank(cell.value) && !cell.badge && !cell.action}
							>
								{#if cell.badge}
									<Badge label={cell.badge.label} tone={cell.badge.tone} />
								{:else if cell.action && cell.file}
									<button
										type="button"
										class="link"
										style="font-weight:400;word-break:break-word;display:inline-flex;gap:6px;align-items:flex-start;min-width:150px"
										title={cell.actionTitle}
										on:click|stopPropagation={cell.action}
										><Icon name="doc" size={14} stroke={1.8} /><span>{display(cell.value)}</span
										></button
									>
								{:else if cell.action}
									<button
										type="button"
										class="num-link"
										title={cell.actionTitle}
										on:click|stopPropagation={cell.action}>{display(cell.value)}</button
									>
								{:else if cell.bold}
									<b>{display(cell.value)}</b>
								{:else}
									{display(cell.value)}
								{/if}
								{#if cell.subtitle}<div class="sub">{cell.subtitle}</div>{/if}
							</td>
						{/each}
					</tr>
				{/each}
				{#if totals}
					<tr class="total">
						{#each totals as rawCell, index}
							<td class:r={headers[index]?.alignRight}>{toObject(rawCell).value ?? ''}</td>
						{/each}
					</tr>
				{/if}
			</tbody>
		</table>
	</div>
</div>
