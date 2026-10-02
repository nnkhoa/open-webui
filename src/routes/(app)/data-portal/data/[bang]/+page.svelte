<script lang="ts">
	// Dữ liệu — chi tiết bảng (đặc tả 19.2), Giải thích các cột (MH-32), xem tệp vừa tải (MH-33).
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { dpNhom, dpNam, dpDomains, dpNap, NAP_TRONG } from '$lib/stores/dataPortal';
	import { dpGet, dpDownload, luuTep } from '$lib/apis/data-portal';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import GroupYearChips from '$lib/components/data-portal/GroupYearChips.svelte';
	import Dropdown from '$lib/components/data-portal/Dropdown.svelte';
	import SearchBox from '$lib/components/data-portal/SearchBox.svelte';
	import Pager from '$lib/components/data-portal/Pager.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Drawer from '$lib/components/data-portal/Drawer.svelte';
	import Dialog from '$lib/components/data-portal/Dialog.svelte';
	import ExcelGrid from '$lib/components/data-portal/ExcelGrid.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import { so, soTien, tyLe, ngay, thoiGian } from '$lib/components/data-portal/fmt';

	type Cot = {
		ten: string;
		ten_nbc: string;
		kieu: string; // text | int | money | ratio | date …
		kieu_hien?: string; // chữ hiện ở "Kiểu dữ liệu: …"
		bat_buoc: boolean;
		y_nghia: string;
		dung_de: string;
		vi_du: string | null;
		so_do: boolean;
	};
	type Bang = {
		bang: string;
		ten: string;
		mo_ta: string;
		moi_dong_la: string;
		nhom: string;
		loai: 'fact' | 'dim';
		loai_tep: { ma: string; ten: string; phu?: string } | null;
		lop: string;
		nam?: number | null;
		thang_moi_nhat: string | null;
		cap_nhat: string | null;
		co_ky: boolean;
		ky_ds: string[];
		cot: Cot[];
		tong: number;
		dong: (string | number | null)[][];
		dong_tong: (string | number | null)[] | null;
	};

	const NHAN_LOP: Record<string, string> = { gold: 'Dữ liệu phân tích', silver: 'Dữ liệu chuẩn hoá', bronze: 'Dữ liệu gốc' };

	$: ten = $page.params.bang ?? '';
	$: sp = $page.url.searchParams;
	let lop = 'gold';
	let ky = '';
	let tim = '';
	let trang = 1;
	let moi = 50;
	let b: Bang | null = null;
	let loi = '';
	let gt = false;
	let xem: { ten: string; sheets: { ten: string; cot: string[]; dong: { rn: number; cells: (string | null)[] }[] }[]; tab: number; soDong: number } | null = null;

	let khoiTao = '';
	$: if (khoiTao !== ten) {
		khoiTao = ten;
		lop = sp.get('lop') ?? 'gold';
		ky = sp.get('ky') ?? '';
		tim = sp.get('tim') ?? '';
		if (sp.has('nam')) dpNam.set(sp.get('nam') ?? '');
		trang = 1;
	}

	const tai = async (bang: string, l: string, nam: string, k: string, t: string, tr: number, m: number) => {
		try {
			loi = '';
			b = await dpGet<Bang>(`tables/${bang}`, { lop: l, nam, ky: k, tim: t, trang: tr, moi: m });
			if (b.nhom && b.nhom !== $dpNhom) dpNhom.set(b.nhom);
		} catch (e) {
			loi = (e as Error).message;
		}
	};
	$: tai(ten, lop, b?.loai === 'dim' ? '' : $dpNam, ky, tim, trang, moi);

	$: dangLoc = !!(ky || tim);
	$: ghi = b
		? [
				b.loai_tep ? `${b.loai_tep.ten} · ${b.loai_tep.phu ?? ''}` : '',
				b.loai === 'dim' ? 'Dùng chung mọi năm' : $dpNam ? `Năm ${$dpNam}` : 'Tất cả năm',
				b.co_ky && b.thang_moi_nhat ? `Tháng mới nhất ${b.thang_moi_nhat}` : '',
				b.cap_nhat ? `Cập nhật ${thoiGian(b.cap_nhat)}` : '',
				NHAN_LOP[lop]
			]
				.filter(Boolean)
				.join(' · ')
		: '';

	const hienO = (v: unknown, c: Cot) => {
		if (v === null || v === undefined || v === '') return '—';
		if (c.kieu === 'ratio') return tyLe(v);
		if (c.kieu === 'date') return ngay(v);
		if (typeof v === 'number') return c.kieu === 'money' ? soTien(v) : so(v);
		return String(v);
	};
	const phai = (c: Cot) => ['int', 'money', 'ratio', 'number'].includes(c.kieu) && lop !== 'bronze';
	const xoaLoc = () => {
		ky = '';
		tim = '';
		trang = 1;
	};
	const napDuLieu = () => {
		dpNap.set({ ...NAP_TRONG });
		goto('/data-portal/upload');
	};

	const taiExcel = async () => {
		const { blob, ten: tenTep, soDong } = await dpDownload(`tables/${ten}/export.xlsx`, { lop, nam: b?.loai === 'dim' ? '' : $dpNam, ky, tim }, `${ten}.xlsx`);
		luuTep(blob, tenTep);
		try {
			const XLSX = await import('xlsx');
			const wb = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
			const sheets = wb.SheetNames.map((sn) => {
				const ws = wb.Sheets[sn];
				const aoa = XLSX.utils.sheet_to_json<(string | number | null)[]>(ws, { header: 1, raw: false, defval: null });
				const n = Math.max(0, ...aoa.map((r) => r.length));
				const cot = Array.from({ length: n }, (_, i) => XLSX.utils.encode_col(i));
				return { ten: sn, cot, dong: aoa.slice(0, 500).map((r, i) => ({ rn: i + 1, cells: r.map((v) => (v === null ? null : String(v))) })) };
			});
			xem = { ten: tenTep, sheets, tab: 0, soDong: Number.isNaN(soDong) ? (b?.tong ?? 0) : soDong };
		} catch {
			/* không xem trước được thì chỉ tải về */
		}
	};
</script>

{#if loi}
	<Banner k="err" icon="x" title={loi} />
{:else if !b}
	<p class="desc">Đang tải dữ liệu…</p>
{:else}
	<HeaderCard title={b.ten} desc={b.mo_ta} back={() => history.back()}>
		<svelte:fragment slot="actions">
			<button type="button" class="btn" title="Ý nghĩa, kiểu dữ liệu và ví dụ của từng cột" on:click={() => (gt = true)}><Icon name="cols" size={16} />Giải thích các cột</button>
			<button type="button" class="btn primary" title="Tải đúng các dòng đang lọc, kèm sheet THONG_TIN" on:click={taiExcel}><Icon name="down" size={16} />Tải Excel</button>
		</svelte:fragment>
	</HeaderCard>

	<div class="chiprow" aria-label="Bộ lọc">
		<GroupYearChips khoaNam={b.loai === 'dim'} on:nhom={() => goto('/data-portal/data')} on:nam={() => (trang = 1)} />
		<Dropdown
			chip="Lớp dữ liệu"
			title="Xem bảng ở lớp"
			value={lop}
			mac="gold"
			options={[
				{ v: 'gold', t: NHAN_LOP.gold },
				{ v: 'silver', t: NHAN_LOP.silver },
				{ v: 'bronze', t: NHAN_LOP.bronze }
			]}
			on:change={(e) => { lop = e.detail; trang = 1; }}
		/>
		{#if b.co_ky}
			<Dropdown
				chip="Tháng"
				value={ky}
				mac=""
				options={[{ v: '', t: 'Tất cả' }, ...b.ky_ds.map((k) => ({ v: k, t: `Tháng ${k}` }))]}
				on:change={(e) => { ky = e.detail; trang = 1; }}
			/>
		{/if}
		<SearchBox value={tim} placeholder="Tìm theo mã hoặc tên, Enter để tìm" on:search={(e) => { tim = e.detail; trang = 1; }} />
		{#if dangLoc}<button type="button" class="xoa" on:click={xoaLoc}>Xoá bộ lọc</button>{/if}
	</div>

	<section class="card">
		<div class="card-h">
			<div>
				<h2>{so(b.tong)} dòng</h2>
				<div class="sub">{ghi}</div>
			</div>
		</div>
		<div class="tw scroll">
			<div class="tbox">
				<table>
					<thead>
						<tr>{#each b.cot as c}<th class:r={phai(c)} title={c.ten_nbc}>{c.ten}</th>{/each}</tr>
					</thead>
					<tbody>
						{#each b.dong as r}
							<tr>
								{#each r as v, j}
									<td
										class:r={phai(b.cot[j])}
										class:s={j === 0}
										class:neg={b.cot[j].so_do && typeof v === 'number' && v < 0}
										style={v === null || v === '' ? 'color:var(--faint)' : ''}>{hienO(v, b.cot[j])}</td
									>
								{/each}
							</tr>
						{:else}
							<tr>
								<td colspan={b.cot.length} style="text-align:center;padding:24px;color:var(--muted)">
									{#if dangLoc}
										Không có dòng nào khớp bộ lọc. <button type="button" class="link" on:click={xoaLoc}>Xoá bộ lọc</button>
									{:else if $dpNam && b.loai === 'fact'}
										Năm {$dpNam} chưa có dữ liệu. <button type="button" class="link" on:click={napDuLieu}>Nạp dữ liệu</button> hoặc chọn năm khác.
									{:else}
										Bảng chưa có dòng nào. <button type="button" class="link" on:click={napDuLieu}>Nạp dữ liệu</button>
									{/if}
								</td>
							</tr>
						{/each}
						{#if dangLoc && b.tong && b.dong_tong && lop !== 'bronze'}
							<tr class="tong">
								{#each b.dong_tong as v, j}
									<td class:r={j > 0} class:neg={typeof v === 'number' && v < 0}
										>{j === 0 ? 'Tổng dữ liệu đang lọc' : v === null ? '' : hienO(v, b.cot[j])}</td
									>
								{/each}
							</tr>
						{/if}
					</tbody>
				</table>
			</div>
		</div>
		{#if b.tong}
			<Pager tong={b.tong} {trang} {moi} on:change={(e) => { trang = e.detail.trang; moi = e.detail.moi; }} />
		{/if}
	</section>
{/if}

{#if gt && b}
	<Drawer label="Giải thích các cột" on:close={() => (gt = false)}>
		<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
			<h2 style="margin:0;font-size:18px;font-weight:500">Giải thích các cột</h2>
			<button type="button" class="btn sm" on:click={() => (gt = false)}>Đóng</button>
		</div>
		<p class="desc" style="font-size:13px;margin-bottom:10px">{b.ten} — {b.moi_dong_la || b.mo_ta}</p>
		{#each b.cot as c}
			<div class="gt">
				<b>{c.ten}</b>
				<div>Tên trong tệp NBC: {c.ten_nbc}</div>
				<div>Kiểu dữ liệu: {c.kieu_hien ?? c.kieu}{c.bat_buoc ? ' · cột định danh, bắt buộc' : ''}</div>
				<div>{c.y_nghia}</div>
				<div>Dùng để: {c.dung_de}</div>
				{#if c.vi_du}<div>Ví dụ: <code>{c.vi_du}</code></div>{/if}
			</div>
		{/each}
	</Drawer>
{/if}

{#if xem}
	<Dialog wide label="Xem tệp vừa tải" on:close={() => (xem = null)}>
		<div style="display:flex;gap:12px;align-items:center">
			<span class="fileic"><Icon name="doc" size={20} /></span>
			<div style="min-width:0">
				<h2 style="word-break:break-all">{xem.ten}</h2>
				<p class="desc">Đã tải về · {so(xem.soDong)} dòng · {xem.sheets.length} sheet</p>
			</div>
		</div>
		<div class="subtabs" style="padding:0">
			{#each xem.sheets as s, i}
				<button type="button" class="subtab" class:on={i === xem.tab} on:click={() => xem && (xem.tab = i)}>{s.ten}</button>
			{/each}
		</div>
		<ExcelGrid cols={xem.sheets[xem.tab].cot} rows={xem.sheets[xem.tab].dong} />
		<div class="row" style="justify-content:flex-end">
			<button type="button" class="btn" on:click={() => (xem = null)}>Đóng</button>
		</div>
	</Dialog>
{/if}
