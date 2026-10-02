<script lang="ts">
	// Các thẻ "Đối chiếu tệp gốc ↔ database" (đặc tả mục 18). Dữ liệu và tiêu đề do API trả.
	import { goto } from '$app/navigation';
	import Card from './Card.svelte';
	import DataTable, { type Row, type Cell } from './DataTable.svelte';
	import Dropdown from './Dropdown.svelte';
	import Pager from './Pager.svelte';
	import { dpGet } from '$lib/apis/data-portal';
	import { soTien, mauKetLuan } from './fmt';

	type Mo = { bang?: string; lop?: string; nam?: string; ky?: string; tim?: string; sheet?: number };
	type O = string | number | null | { v: string | number | null; mo?: Mo; phu?: string };
	type The = {
		ma: string;
		tieu_de: string;
		so?: string | number;
		thong_bao?: string;
		cot: { t: string; r?: boolean }[];
		dong: { o: O[]; ket_luan?: string; ket_luan_phu?: string; phu?: string; mo?: Mo }[];
		tong?: O[];
		tuy_chon?: { ten: string; nhan: string; gia_tri: string; mac?: string; lua_chon: { v: string; t: string; phu?: string }[] }[];
		trang?: { trang: number; moi: number; tong: number };
	};

	export let loadId: number;
	export let nam: string | number = '';

	let the: The[] = [];
	let dangTai = true;
	let loi = '';
	let thamSo: Record<string, Record<string, string | number>> = {};

	const tai = async (ma?: string) => {
		try {
			if (ma) {
				const kq = await dpGet<{ the: The[] }>(`loads/${loadId}/reconcile`, { the: ma, ...thamSo[ma] });
				the = the.map((t) => kq.the.find((k) => k.ma === t.ma) ?? t);
			} else {
				dangTai = true;
				the = (await dpGet<{ the: The[] }>(`loads/${loadId}/reconcile`)).the;
			}
		} catch (e) {
			loi = (e as Error).message;
		} finally {
			dangTai = false;
		}
	};
	$: loadId, tai();

	const moToi = (m?: Mo) => {
		if (!m) return undefined;
		if (m.sheet !== undefined) return () => goto(`/data-portal/history/${loadId}/file?sheet=${m.sheet}`);
		if (m.bang) {
			const q = new URLSearchParams();
			q.set('lop', m.lop ?? 'gold');
			if (m.nam ?? nam) q.set('nam', String(m.nam ?? nam));
			if (m.ky) q.set('ky', m.ky);
			if (m.tim) q.set('tim', m.tim);
			return () => goto(`/data-portal/data/${m.bang}?${q.toString()}`);
		}
		return undefined;
	};
	const hien = (v: unknown) => (typeof v === 'number' ? soTien(v) : (v ?? '—'));
	const o2c = (o: O, i: number, phu?: string): Cell => {
		if (o !== null && typeof o === 'object') {
			return { v: hien(o.v) as string, link: moToi(o.mo), sub: o.phu, bold: i === 0, cls: 's' };
		}
		return i === 0 ? { v: hien(o) as string, bold: true, sub: phu, cls: 's' } : (hien(o) as string);
	};
	const rows = (t: The): Row[] =>
		t.dong.map((d) => ({
			cells: [
				...d.o.map((o, i) => o2c(o, i, i === 0 ? d.phu : undefined)),
				...(d.ket_luan !== undefined ? [{ badge: [d.ket_luan, mauKetLuan(d.ket_luan)] as [string, string], sub: d.ket_luan_phu }] : [])
			],
			onClick: moToi(d.mo)
		}));
</script>

{#if dangTai}
	<p class="desc" style="padding:0 24px 20px">Đang tải…</p>
{:else if loi}
	<p class="desc" style="padding:0 24px 20px">{loi}</p>
{:else}
	{#each the as t (t.ma)}
		{#if t.thong_bao}
			<Card title={t.ma === 'tu_choi' ? '' : t.tieu_de}><p class="desc">{t.thong_bao}</p></Card>
		{:else}
			<Card title={t.tieu_de} count={t.so ?? ''} pad={false}>
				{#if t.tuy_chon?.length}
					<div class="chiprow" style="padding:0 24px 14px">
						{#each t.tuy_chon as c (c.ten)}
							<Dropdown
								chip={c.nhan}
								value={c.gia_tri}
								mac={c.mac ?? c.lua_chon[0]?.v ?? c.gia_tri}
								options={c.lua_chon}
								on:change={(e) => {
									thamSo[t.ma] = { ...(thamSo[t.ma] ?? {}), [c.ten]: e.detail, trang: 1 };
									tai(t.ma);
								}}
							/>
						{/each}
					</div>
				{/if}
				<DataTable heads={t.cot} rows={rows(t)} tong={t.tong ? t.tong.map((o, i) => o2c(o, i)) : null} />
				{#if t.trang && t.trang.tong > t.trang.moi}
					<Pager
						tong={t.trang.tong}
						trang={t.trang.trang}
						moi={t.trang.moi}
						on:change={(e) => {
							thamSo[t.ma] = { ...(thamSo[t.ma] ?? {}), trang: e.detail.trang, moi: e.detail.moi };
							tai(t.ma);
						}}
					/>
				{/if}
			</Card>
		{/if}
	{/each}
{/if}
