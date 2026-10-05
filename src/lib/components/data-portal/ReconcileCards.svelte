<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';

	import { getLoadReconciliation } from '$lib/apis/data-portal';
	import type {
		CardCell,
		CardLink,
		CardOption,
		ReconcileCard,
		ReconcileQuery
	} from '$lib/apis/data-portal/types';

	import Card from './Card.svelte';
	import DataTable, { type TableCell, type TableRow } from './DataTable.svelte';
	import Dropdown from './Dropdown.svelte';
	import Pager from './Pager.svelte';
	import { formatAmount, verdictTone } from './format';

	const i18n: Writable<i18nType> = getContext('i18n');

	const REJECTED_CARD = 'rejected';
	const DEFAULT_LAYER = 'gold';

	export let loadId: number;
	export let year: string | number | null = '';

	let cards: ReconcileCard[] = [];
	let loading = true;
	let errorMessage = '';
	let queries: Record<string, ReconcileQuery> = {};

	$: loadCards(loadId);

	const loadCards = async (id: number) => {
		loading = true;
		try {
			cards = (await getLoadReconciliation(localStorage.token, id)).cards;
		} catch (error) {
			errorMessage = (error as Error).message;
		} finally {
			loading = false;
		}
	};

	const reloadCard = async (key: string) => {
		try {
			const result = await getLoadReconciliation(localStorage.token, loadId, {
				card: key,
				...queries[key]
			});
			cards = cards.map((card) => result.cards.find((updated) => updated.key === card.key) ?? card);
		} catch (error) {
			errorMessage = (error as Error).message;
		} finally {
			loading = false;
		}
	};

	const updateQuery = (key: string, changes: ReconcileQuery) => {
		queries[key] = { ...(queries[key] ?? {}), ...changes };
		reloadCard(key);
	};

	const openLink = (link?: CardLink) => {
		if (!link) return undefined;
		if ('sheet' in link) {
			return () => goto(`/data-portal/history/${loadId}/file?sheet=${link.sheet}`);
		}
		if (link.table) {
			const params = new URLSearchParams();
			params.set('layer', link.layer ?? DEFAULT_LAYER);
			const linkYear = link.year ?? year;
			if (linkYear) params.set('year', String(linkYear));
			if (link.period) params.set('period', String(link.period));
			if (link.query) params.set('query', link.query);
			return () => goto(`/data-portal/data/${link.table}?${params.toString()}`);
		}
		return undefined;
	};

	const display = (value: unknown) =>
		typeof value === 'number' ? formatAmount(value) : String(value ?? '—');

	const toTableCell = (cell: CardCell, index: number, note?: string): TableCell => {
		if (cell !== null && typeof cell === 'object') {
			return {
				value: display(cell.value),
				action: openLink(cell.link),
				bold: index === 0,
				className: 's'
			};
		}
		return index === 0
			? { value: display(cell), bold: true, subtitle: note, className: 's' }
			: display(cell);
	};

	const tableRows = (card: ReconcileCard): TableRow[] =>
		card.rows.map((row) => ({
			cells: [
				...row.cells.map((cell, index) =>
					toTableCell(cell, index, index === 0 ? row.note : undefined)
				),
				...(row.verdict !== undefined
					? [
							{
								badge: { label: row.verdict, tone: verdictTone(row.verdict) },
								subtitle: row.verdict_note
							}
						]
					: [])
			],
			onClick: openLink(row.link)
		}));

	const optionDefault = (option: CardOption) =>
		option.default ?? option.choices[0]?.value ?? option.value;
</script>

{#if loading}
	<p class="desc" style="padding:0 24px 20px">{$i18n.t('Loading…')}</p>
{:else if errorMessage}
	<p class="desc" style="padding:0 24px 20px">{errorMessage}</p>
{:else}
	{#each cards as card (card.key)}
		{#if card.message}
			<Card title={card.key === REJECTED_CARD ? '' : card.title}
				><p class="desc">{card.message}</p></Card
			>
		{:else}
			<Card title={card.title} count={card.count ?? ''} padded={false}>
				{#if card.options?.length}
					<div class="chiprow" style="padding:0 24px 14px">
						{#each card.options as option (option.name)}
							<Dropdown
								chipLabel={option.label}
								value={option.value}
								defaultValue={optionDefault(option)}
								options={option.choices}
								on:change={(event) =>
									updateQuery(card.key, { [option.name]: event.detail, page: 1 })}
							/>
						{/each}
					</div>
				{/if}
				<DataTable
					headers={card.columns.map((column) => ({
						label: column.label,
						alignRight: column.align_right
					}))}
					rows={tableRows(card)}
					totals={card.totals ? card.totals.map((cell, index) => toTableCell(cell, index)) : null}
				/>
				{#if card.pagination && card.pagination.total > card.pagination.page_size}
					<Pager
						total={card.pagination.total}
						page={card.pagination.page}
						pageSize={card.pagination.page_size}
						on:change={(event) =>
							updateQuery(card.key, { page: event.detail.page, page_size: event.detail.pageSize })}
					/>
				{/if}
			</Card>
		{/if}
	{/each}
{/if}
