<script context="module" lang="ts">
	export type CellObj = {
		v?: string | number | null;
		sub?: string;
		badge?: [string, string];
		link?: () => void;
		linkTitle?: string;
		cls?: string;
		mono?: boolean;
		bold?: boolean;
		tep?: boolean; // tên tệp bấm được, có biểu tượng tệp
	};
	export type Cell = string | number | null | undefined | CellObj;
	export type Row = { cells: Cell[]; onClick?: () => void; title?: string };
</script>

<script lang="ts">
	// Bảng dùng chung (đặc tả 12.6). Ô là chữ thuần (Svelte tự thoát ký tự) hoặc dạng có cấu trúc.
	import Badge from './Badge.svelte';
	import Icon from './Icon.svelte';

	export let heads: { t: string; r?: boolean; title?: string }[] = [];
	export let rows: Row[] = [];
	export let tong: Cell[] | null = null;
	export let empty = '';
	export let cls = '';

	const o = (c: Cell): CellObj => (c !== null && typeof c === 'object' ? c : { v: c });
	const hien = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));
	const trong = (v: unknown) => v === null || v === undefined || v === '';
</script>

<div class="tw {cls}">
	<div class="tbox">
		<table>
			<thead>
				<tr>
					{#each heads as h}<th class:r={h.r} title={h.title}>{h.t}</th>{/each}
				</tr>
			</thead>
			<tbody>
				{#each rows as row}
					<tr
						class:rc={!!row.onClick}
						tabindex={row.onClick ? 0 : undefined}
						title={row.onClick ? row.title || 'Bấm để mở' : undefined}
						on:click={row.onClick}
						on:keydown={(e) => {
							if (row.onClick && e.key === 'Enter') row.onClick();
						}}
					>
						{#each row.cells as c, i}
							{@const x = o(c)}
							<td
								class="{heads[i]?.r ? 'r ' : ''}{x.cls ?? ''}"
								class:muted={trong(x.v) && !x.badge && !x.link}
							>
								{#if x.badge}
									<Badge t={x.badge[0]} k={x.badge[1]} />
								{:else if x.link && x.tep}
									<button
										type="button"
										class="link"
										style="font-weight:400;word-break:break-word;display:inline-flex;gap:6px;align-items:flex-start;min-width:150px"
										title={x.linkTitle}
										on:click|stopPropagation={x.link}><Icon name="doc" size={14} stroke={1.8} /><span>{hien(x.v)}</span></button
									>
								{:else if x.link}
									<button
										type="button"
										class="num-link"
										title={x.linkTitle}
										on:click|stopPropagation={x.link}>{hien(x.v)}</button
									>
								{:else if x.bold}
									<b>{hien(x.v)}</b>
								{:else if x.mono}
									<span class="mono">{hien(x.v)}</span>
								{:else}
									{hien(x.v)}
								{/if}
								{#if x.sub}<div class="sub">{x.sub}</div>{/if}
							</td>
						{/each}
					</tr>
				{:else}
					{#if empty}
						<tr><td colspan={heads.length} style="text-align:center;color:var(--muted);padding:24px">{empty}</td></tr>
					{/if}
				{/each}
				{#if tong}
					<tr class="tong">
						{#each tong as c, i}
							{@const x = o(c)}
							<td class:r={heads[i]?.r}>{x.v ?? ''}</td>
						{/each}
					</tr>
				{/if}
			</tbody>
		</table>
	</div>
</div>
