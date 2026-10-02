<script lang="ts">
	// Nạp dữ liệu — bước 3: Xác nhận thêm mới dữ liệu (đặc tả 15.3).
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { dpNap, dpDomains, NAP_TRONG } from '$lib/stores/dataPortal';
	import { dpGet, dpSend, dpUpload, DpError } from '$lib/apis/data-portal';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import StepBar from '$lib/components/data-portal/StepBar.svelte';
	import ReadonlyCard from '$lib/components/data-portal/ReadonlyCard.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import DataTable, { type Row, type Cell } from '$lib/components/data-portal/DataTable.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import { so, soTien, kb, thoiGian } from '$lib/components/data-portal/fmt';

	type LoaiTep = { ma: string; ten: string; phu?: string };
	type HienCo = { so_dong: number; load_id: number; luc: string; nguoi: string } | null;
	type TepCho = {
		ma_tep_cho: string;
		nhom: string;
		nam: string | number;
		loai: LoaiTep;
		ten_tep: string;
		size_bytes: number;
		sheet: string | null;
		kiem_tra: {
			bang: string;
			ten_bang: string;
			sheet: string;
			doc: number;
			thieu_bat_buoc: number;
			trung_bo: number;
			o_trong: number;
			o_trong_chi_tiet: { cot: string; so_o: number }[];
			se_ghi: number;
			tong: number | null;
			ket_luan: string;
		}[];
		giong_het: { load_id: number; luc: string; nguoi: string } | null;
		ghi_de: (string | number)[];
		moi: (string | number)[];
		truoc: { load_id: number; so_dong: number; luc: string; nguoi: string } | null;
		theo_nhom: {
			tieu_de: string;
			cot_dau: string;
			dong: {
				nhom: string;
				phu?: string;
				du_lieu?: string;
				so_dong: number;
				so_cot?: number;
				so_cot_tong?: number;
				so_luong?: number;
				hien_co: HienCo;
				cach_ghi: string;
			}[];
			tong?: { so_dong: number; so_luong?: number; hien_co?: number | null };
		};
	};

	let x: TepCho | null = null;
	let loi = '';
	let ban = false;

	$: ma = $page.params.ma;
	onMount(async () => {
		try {
			if (!$dpDomains.length) dpDomains.set(await dpGet('domains'));
			x = await dpGet<TepCho>(`uploads/${ma}`);
		} catch (e) {
			loi = (e as Error).message;
		}
	});

	$: dom = $dpDomains.find((d) => d.code === x?.nhom);
	$: gc = (dom?.loai_tep?.length ?? 0) > 1;
	$: loaiKia = dom?.loai_tep?.find((l) => l.ma !== x?.loai?.ma)?.ten ?? '';
	const ds = (a: (string | number)[]) => a.join(', ');

	const veBuoc1 = () => goto('/data-portal/upload');
	const huy = async () => {
		ban = true;
		try {
			await dpSend('DELETE', `uploads/${ma}`);
		} catch {
			/* tệp chờ đã không còn: vẫn về bước 1 */
		}
		dpNap.update((s) => ({ ...s, file: null, luc: '' }));
		goto('/data-portal/upload');
	};
	const kiemLai = async () => {
		const n = $dpNap;
		if (!n.file) return veBuoc1();
		ban = true;
		const f = new FormData();
		f.set('nhom', n.nhom);
		f.set('nam', n.nam);
		if (x?.loai) f.set('loai', x.loai.ma);
		f.set('file', n.file);
		try {
			await dpSend('DELETE', `uploads/${ma}`).catch(() => null);
			const kq = await dpUpload<{ ma_tep_cho?: string; load_id?: number }>('uploads', f);
			if (kq.ma_tep_cho) {
				x = null;
				await goto(`/data-portal/upload/confirm/${kq.ma_tep_cho}`, { replaceState: true });
				x = await dpGet<TepCho>(`uploads/${kq.ma_tep_cho}`);
			} else if (kq.load_id) {
				dpNap.set({ ...NAP_TRONG });
				goto(`/data-portal/upload/result/${kq.load_id}`);
			}
		} catch (e) {
			loi = e instanceof DpError ? e.message : String(e);
		} finally {
			ban = false;
		}
	};
	const xacNhan = async () => {
		ban = true;
		try {
			const kq = await dpSend<{ load_id: number }>('POST', `uploads/${ma}/confirm`);
			dpNap.set({ ...NAP_TRONG });
			if (kq) goto(`/data-portal/upload/result/${kq.load_id}`);
		} catch (e) {
			loi = e instanceof DpError ? e.message : String(e);
			ban = false;
		}
	};

	const hienCo = (h: HienCo): Cell =>
		h ? { v: `${so(h.so_dong)} dòng`, sub: `lần nạp #${h.load_id} · ${thoiGian(h.luc)} · ${h.nguoi}`, cls: 's' } : '—';
	const cachGhi = (t: string): Cell => ({ badge: [t, t === 'Ghi đè' ? 'warn' : 'ok'] });

	$: ktRows = (x?.kiem_tra ?? []).map(
		(k): Row => ({
			cells: gc
				? [
						{ v: k.ten_bang, bold: true, cls: 's' },
						so(k.doc),
						so(k.thieu_bat_buoc),
						so(k.trung_bo),
						{
							v: so(k.o_trong),
							sub: k.o_trong_chi_tiet?.length
								? 'không đọc được: ' + k.o_trong_chi_tiet.map((o) => `${o.cot} ${o.so_o}`).join(' · ')
								: undefined
						},
						so(k.se_ghi),
						so(k.tong),
						{ badge: [k.ket_luan, 'ok'] }
					]
				: [
						{ v: k.ten_bang, cls: 's' },
						k.sheet,
						so(k.doc),
						so(k.thieu_bat_buoc),
						so(k.trung_bo),
						so(k.se_ghi),
						k.tong === null ? '—' : soTien(k.tong),
						{ badge: [k.ket_luan, 'ok'] }
					]
		})
	);
	$: ktTong = !gc && x
		? [
				{ v: 'Tổng' },
				'',
				so(x.kiem_tra.reduce((a, k) => a + k.doc, 0)),
				so(x.kiem_tra.reduce((a, k) => a + k.thieu_bat_buoc, 0)),
				so(x.kiem_tra.reduce((a, k) => a + k.trung_bo, 0)),
				so(x.kiem_tra.reduce((a, k) => a + k.se_ghi, 0)),
				'',
				''
			]
		: null;

	$: nhomRows = (x?.theo_nhom?.dong ?? []).map((d, i, arr): Row => {
		if (!gc) {
			const dau = i === 0 || arr[i - 1].nhom !== d.nhom;
			return {
				cells: [
					dau ? { v: d.nhom, bold: true, cls: 's' } : '',
					{ v: d.du_lieu ?? '', cls: 's' },
					so(d.so_dong),
					`${so(d.so_cot)} / ${so(d.so_cot_tong)}`,
					hienCo(d.hien_co),
					cachGhi(d.cach_ghi)
				]
			};
		}
		return {
			cells: [{ v: d.nhom, bold: true, sub: d.phu, cls: 's' }, so(d.so_dong), so(d.so_luong), hienCo(d.hien_co), cachGhi(d.cach_ghi)]
		};
	});
	$: nhomTong =
		gc && x?.theo_nhom?.tong
			? [
					'Tổng',
					so(x.theo_nhom.tong.so_dong),
					so(x.theo_nhom.tong.so_luong),
					x.theo_nhom.tong.hien_co ? so(x.theo_nhom.tong.hien_co) : '—',
					''
				]
			: null;
</script>

<HeaderCard title="Xác nhận nạp dữ liệu" back={veBuoc1}>
	<svelte:fragment slot="actions">
		<button type="button" class="btn danger" disabled={ban} title="Bỏ tệp này. Dữ liệu trong database giữ nguyên." on:click={huy}>Huỷ, không nạp</button>
		<button type="button" class="btn primary" disabled={ban || !x} on:click={xacNhan}><Icon name="up" size={16} />Xác nhận thêm mới dữ liệu</button>
	</svelte:fragment>
</HeaderCard>

<StepBar
	i={2}
	{gc}
	quay={{
		0: { title: gc ? 'Về bước 1: đổi nhóm, năm, loại tệp hoặc tệp' : 'Về bước 1: đổi nhóm, năm hoặc tệp', onClick: veBuoc1 },
		1: { title: 'Chạy lại bước Kiểm tra tệp', onClick: kiemLai }
	}}
/>

{#if loi}<Banner k="err" icon="x" title={loi} />{/if}

{#if !x && !loi}
	<p class="desc">Đang tải dữ liệu…</p>
{:else if x}
	<ReadonlyCard
		title="Thông tin tệp chờ xác nhận"
		fields={gc
			? [
					{ l: 'Nhóm thông tin', v: `${dom?.code} · ${dom?.name}` },
					{ l: 'Năm dữ liệu', v: x.nam },
					{ l: 'Loại tệp', v: x.loai?.ten ?? '' },
					{ l: 'Lấy từ sheet', v: x.sheet ?? '—' },
					{ l: 'Tên tệp', v: x.ten_tep },
					{ l: 'Dung lượng', v: kb(x.size_bytes) }
				]
			: [
					{ l: 'Nhóm thông tin', v: `${dom?.code} · ${dom?.name}` },
					{ l: 'Loại file', v: x.loai?.ten ?? '' },
					{ l: 'Năm dữ liệu', v: x.nam },
					{ l: 'Tên tệp', v: x.ten_tep, span: 2 },
					{ l: 'Dung lượng', v: kb(x.size_bytes) }
				]}
	/>

	<Card title="Kết quả kiểm tra dữ liệu trong tệp" pad={false}>
		<DataTable
			heads={gc
				? [
						{ t: 'Bảng' },
						{ t: 'Số dòng đọc được', r: true },
						{ t: 'Thiếu giá trị bắt buộc', r: true },
						{ t: 'Dòng trùng sẽ bỏ', r: true },
						{ t: 'Ô để trống', r: true },
						{ t: 'Số dòng sẽ ghi', r: true },
						{ t: 'Tổng số lượng', r: true },
						{ t: 'Kết luận' }
					]
				: [
						{ t: 'Bảng' },
						{ t: 'Lấy từ sheet' },
						{ t: 'Số dòng đọc được', r: true },
						{ t: 'Thiếu giá trị bắt buộc', r: true },
						{ t: 'Dòng trùng sẽ bỏ', r: true },
						{ t: 'Số dòng sẽ ghi', r: true },
						{ t: 'Tổng tiền trong tệp', r: true },
						{ t: 'Kết luận' }
					]}
			rows={ktRows}
			tong={ktTong}
		/>
	</Card>

	{#if x.giong_het}
		<Banner
			k="warn"
			icon="alert"
			title="Tệp này giống hệt lần nạp #{x.giong_het.load_id}"
			p="Đã nạp lúc {thoiGian(x.giong_het.luc)} bởi {x.giong_het.nguoi}. Nội dung không đổi nên nạp lại sẽ không thay đổi dữ liệu."
		/>
	{:else if gc && x.truoc}
		<Banner
			k="warn"
			icon="alert"
			title="{x.loai.ten} năm {x.nam} đã có dữ liệu — sẽ bị ghi đè toàn bộ"
			p="{so(x.truoc.so_dong)} dòng của lần nạp #{x.truoc.load_id} sẽ được thay bằng {so(x.theo_nhom?.tong?.so_dong)} dòng trong tệp. {loaiKia} giữ nguyên."
		/>
	{:else if gc}
		<Banner
			k="info"
			icon="info"
			title="{x.loai.ten} năm {x.nam} là dữ liệu mới"
			p="Hệ thống chưa có {x.loai.ten} năm {x.nam}. Nạp sẽ thêm {so(x.theo_nhom?.tong?.so_dong)} dòng. {loaiKia} giữ nguyên."
		/>
	{:else if x.ghi_de.length}
		<Banner
			k="warn"
			icon="alert"
			title="Tháng {ds(x.ghi_de)} năm {x.nam} đã có dữ liệu — sẽ bị ghi đè"
			p="Dữ liệu hiện có của {x.ghi_de.length === 1 ? 'tháng này' : 'các tháng này'} sẽ được thay bằng dữ liệu trong tệp. {x.moi.length ? `Tháng ${ds(x.moi)} là mới. ` : ''}Tháng không có trong tệp giữ nguyên."
		/>
	{:else}
		<Banner
			k="info"
			icon="info"
			title="Tháng {ds(x.moi)} năm {x.nam} là dữ liệu mới"
			p="Hệ thống chưa có dữ liệu của {x.moi.length === 1 ? 'tháng này' : 'các tháng này'}. Nạp sẽ thêm dữ liệu, không ghi đè tháng nào."
		/>
	{/if}

	<Card title={x.theo_nhom?.tieu_de ?? ''} pad={false}>
		<DataTable
			heads={gc
				? [
						{ t: x.theo_nhom.cot_dau },
						{ t: 'Số dòng trong tệp', r: true },
						{ t: 'Số lượng', r: true },
						{ t: 'Hiện có trong hệ thống' },
						{ t: 'Cách ghi dữ liệu khi nạp' }
					]
				: [
						{ t: 'Tháng' },
						{ t: 'Dữ liệu' },
						{ t: 'Số dòng trong tệp', r: true },
						{ t: 'Số cột được sử dụng', r: true },
						{ t: 'Hiện có trong hệ thống' },
						{ t: 'Cách ghi dữ liệu khi nạp' }
					]}
			rows={nhomRows}
			tong={nhomTong}
		/>
	</Card>
{/if}
