<script lang="ts">
	// Tệp gốc của một lần nạp (đặc tả 16.3).
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { dpDomains } from '$lib/stores/dataPortal';
	import { dpGet, dpDownload, luuTep } from '$lib/apis/data-portal';
	import type { LanNap } from '$lib/apis/data-portal/types';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import ReadonlyCard from '$lib/components/data-portal/ReadonlyCard.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import ExcelGrid from '$lib/components/data-portal/ExcelGrid.svelte';
	import Pager from '$lib/components/data-portal/Pager.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import { so, thoiGian } from '$lib/components/data-portal/fmt';

	type Sheet = { so: number; ten: string; so_dong: number; an: boolean; so_dong_an: number };
	type NoiDung = { cot: string[]; tong: number; dong: { rn: number; o: (string | null)[]; an: boolean }[] };

	let L: LanNap | null = null;
	let sheets: Sheet[] = [];
	let nd: NoiDung | null = null;
	let loi = '';
	let trang = 1;
	let moi = 50;
	let dangMo = false;

	$: id = Number($page.params.id);
	$: sheet = Number($page.url.searchParams.get('sheet') ?? '-1');
	$: gc = ($dpDomains.find((d) => d.code === L?.nhom)?.loai_tep?.length ?? 0) > 1;
	$: dom = $dpDomains.find((d) => d.code === L?.nhom);
	$: cur = sheets.find((s) => s.so === sheet) ?? sheets.find((s) => s.ten === L?.sheet) ?? sheets.find((s) => !s.an) ?? sheets[0];

	onMount(async () => {
		try {
			if (!$dpDomains.length) dpDomains.set(await dpGet('domains'));
			[L, sheets] = await Promise.all([dpGet<LanNap>(`loads/${id}`), dpGet<Sheet[]>(`loads/${id}/file/sheets`)]);
		} catch (e) {
			loi = (e as Error).message;
		}
	});

	const taiSheet = async (s: Sheet | undefined, t: number, m: number) => {
		if (!s) return;
		dangMo = true;
		try {
			nd = await dpGet<NoiDung>(`loads/${id}/file/sheets/${s.so}`, { trang: t, moi: m });
		} catch (e) {
			loi = (e as Error).message;
		} finally {
			dangMo = false;
		}
	};
	$: taiSheet(cur, trang, moi);

	const chonSheet = (s: Sheet) => {
		trang = 1;
		goto(`/data-portal/history/${id}/file?sheet=${s.so}`, { replaceState: true, noScroll: true });
	};
	const taiTep = async () => {
		const { blob, ten } = await dpDownload(`loads/${id}/file`, undefined, L?.ten_tep ?? 'tep.xlsx');
		luuTep(blob, ten);
	};
</script>

{#if loi}
	<Banner k="err" icon="x" title={loi} />
{:else if !L}
	<p class="desc">Đang mở tệp…</p>
{:else}
	<HeaderCard title="Tệp gốc · lần nạp #{L.id}" desc={L.ten_tep} back={() => history.back()}>
		<svelte:fragment slot="actions">
			<button type="button" class="btn" on:click={taiTep}><Icon name="down" size={16} />Tải tệp gốc</button>
			<button type="button" class="btn primary" on:click={() => goto(`/data-portal/history/${id}`)}>Xem chi tiết lần nạp</button>
		</svelte:fragment>
	</HeaderCard>

	<ReadonlyCard
		title="Thông tin tệp"
		fields={[
			{ l: 'Nhóm thông tin', v: `${L.nhom} · ${dom?.name ?? ''}` },
			{ l: 'Năm dữ liệu', v: L.nam },
			...(gc ? [{ l: 'Loại tệp', v: L.loai?.ten ?? '' }] : []),
			{ l: 'Người nạp', v: L.nguoi },
			{ l: 'Thời gian nạp', v: thoiGian(L.luc) },
			{ l: 'Số sheet', v: so(sheets.length) }
		]}
	/>

	<section class="card">
		<div class="card-h"><div><h2>Nội dung tệp</h2></div></div>
		<div class="subtabs" role="tablist">
			{#each sheets as s (s.so)}
				<button type="button" role="tab" class="subtab" class:on={s.so === cur?.so} aria-selected={s.so === cur?.so} on:click={() => chonSheet(s)}>
					{s.ten} <span class="count">{so(s.so_dong)}</span>
					{#if s.an}<span class="an-tag">ẩn</span>{/if}
				</button>
			{/each}
		</div>
		{#if cur?.so_dong_an}
			<p class="hint" style="padding:10px 24px 0;margin:0">{so(cur.so_dong_an)} dòng đang bị ẩn trong Excel (chữ nhạt). Portal đọc cả dòng ẩn.</p>
		{/if}
		{#if dangMo && !nd}
			<p class="desc" style="padding:16px 24px">Đang mở tệp…</p>
		{:else if nd}
			<div style="padding:12px 0 0">
				<ExcelGrid cols={nd.cot} rows={nd.dong.map((d) => ({ rn: d.rn, cells: d.o, an: d.an }))} />
			</div>
			<Pager tong={nd.tong} {trang} {moi} on:change={(e) => { trang = e.detail.trang; moi = e.detail.moi; }} />
		{/if}
	</section>
{/if}
