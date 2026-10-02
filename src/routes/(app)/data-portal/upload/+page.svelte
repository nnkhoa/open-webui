<script lang="ts">
	// Nạp dữ liệu — bước 1 và 2 (đặc tả 15.1, 15.2).
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import { dpNap, dpDomains, DP_NAM, NAP_TRONG } from '$lib/stores/dataPortal';
	import { dpGet, dpUpload, DpError, luuTep } from '$lib/apis/data-portal';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import StepBar from '$lib/components/data-portal/StepBar.svelte';
	import Dropdown from '$lib/components/data-portal/Dropdown.svelte';
	import Badge from '$lib/components/data-portal/Badge.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import { kb, noi, thoiGian } from '$lib/components/data-portal/fmt';

	const i18n = getContext('i18n');

	let dangKT = false;
	let buocKT = 0;
	let loiChon = false; // tệp không phải .xlsx
	let loiChung = '';
	let keo = false;

	onMount(async () => {
		if (!$dpDomains.length) {
			try {
				dpDomains.set(await dpGet('domains'));
			} catch (e) {
				loiChung = (e as Error).message;
			}
		}
	});

	$: n = $dpNap;
	$: dom = $dpDomains.find((d) => d.code === n.nhom);
	$: nhieuLoai = (dom?.loai_tep?.length ?? 0) > 1;
	$: loai = dom?.loai_tep?.find((l) => l.ma === n.loai) ?? (!nhieuLoai ? dom?.loai_tep?.[0] : undefined);
	$: thieuDs = [!n.nhom && 'Nhóm thông tin', !n.nam && 'Năm dữ liệu', nhieuLoai && !n.loai && 'Loại tệp'].filter(
		Boolean
	) as string[];
	$: thieuNN = thieuDs.length ? 'Chọn ' + noi(thieuDs) : '';
	$: thieu = thieuNN || (!n.file ? 'Chọn tệp ở mục File đính kèm' : '');
	$: khoaTep = dangKT || !!thieuNN;
	$: hopLe = !!n.file && n.file.name.toLowerCase().endsWith('.xlsx');

	const dat = (patch: Partial<typeof n>) => dpNap.update((s) => ({ ...s, ...patch }));

	const chonTep = (f: File | undefined | null) => {
		if (!f) return;
		if (khoaTep) {
			toast(
				`Chọn Nhóm thông tin${nhieuLoai ? ', Năm dữ liệu và Loại tệp' : ' và Năm dữ liệu'} trước khi chọn tệp.`
			);
			return;
		}
		loiChon = false;
		dat({ file: f, luc: thoiGian(new Date().toISOString()) });
	};

	const kiemTra = async () => {
		if (!n.file) return;
		if (!hopLe) {
			loiChon = true;
			dat({ file: null, luc: '' });
			return;
		}
		loiChon = false;
		dangKT = true;
		buocKT = 0;
		const t = setTimeout(() => (buocKT = 1), 400);
		const form = new FormData();
		form.set('nhom', n.nhom);
		form.set('nam', n.nam);
		if (loai) form.set('loai', loai.ma);
		form.set('file', n.file);
		try {
			const kq = await dpUpload<{ ma_tep_cho?: string; load_id?: number }>('uploads', form);
			if (kq.ma_tep_cho) goto(`/data-portal/upload/confirm/${kq.ma_tep_cho}`);
			else if (kq.load_id) {
				dpNap.set({ ...NAP_TRONG });
				goto(`/data-portal/upload/result/${kq.load_id}`);
			}
		} catch (e) {
			loiChung = e instanceof DpError ? e.message : 'Mất kết nối, chưa xác định được kết quả xử lý.';
		} finally {
			clearTimeout(t);
			dangKT = false;
		}
	};
</script>

<HeaderCard title="Nạp dữ liệu">
	<svelte:fragment slot="actions">
		<button
			type="button"
			class="btn primary"
			disabled={!!thieu || dangKT}
			title={thieu ? thieu + ' để tiếp tục' : 'Đọc tệp và so với dữ liệu đang có. Chưa ghi gì vào database.'}
			on:click={kiemTra}
		>
			{#if dangKT}<span class="spin" aria-hidden="true"></span>Đang kiểm tra…{:else}<Icon name="up" size={16} />Kiểm tra tệp{/if}
		</button>
	</svelte:fragment>
</HeaderCard>

<StepBar i={dangKT ? 1 : 0} gc={nhieuLoai} />

{#if loiChon}
	<Banner k="err" icon="x" title="Không thể chọn tệp này" p="Portal chỉ nhận tệp .xlsx. Hãy mở tệp trong Excel và lưu lại đúng định dạng." />
{/if}
{#if loiChung}
	<Banner k="err" icon="x" title="Không thể kiểm tra tệp" p={loiChung} />
{/if}

{#if dangKT}
	<Card title="Đang kiểm tra tệp">
		<div class="steps">
			<div class="step {buocKT >= 1 ? 'done' : 'on'}"><span class="n">{buocKT >= 1 ? '✓' : '1'}</span>Nhận tệp</div>
			<div class="step {buocKT >= 1 ? 'on' : ''}">
				<span class="n">2</span>Kiểm tra cấu trúc tệp và dữ liệu từng dòng
				{#if buocKT >= 1}<span class="spin" aria-hidden="true"></span>{/if}
			</div>
			<div class="step"><span class="n">3</span>So với dữ liệu đang có</div>
			<p class="desc">Vui lòng giữ nguyên trang. Thời gian xử lý phụ thuộc vào dung lượng tệp.</p>
		</div>
	</Card>
{/if}

<section class="card">
	<div class="card-h">
		<div>
			<h2>Thông tin nạp dữ liệu</h2>
			<div class="sub">
				Vui lòng điền các thông tin bên dưới, thông tin có (<span style="color:var(--req)">*</span>) là bắt buộc.
			</div>
		</div>
	</div>
	<div class="form-grid">
		<div class="field s2">
			<span class="lbl">Nhóm thông tin <span class="req">*</span></span>
			{#if dangKT}
				<div class="ro lk"><Icon name="lock" size={13} />{dom?.code} · {dom?.name}</div>
			{:else}
				<Dropdown
					value={n.nhom}
					placeholder="Chọn nhóm thông tin"
					title="Chọn nhóm thông tin"
					options={$dpDomains.map((d) => ({ v: d.code, t: d.name, ma: d.code, phu: d.phu ?? d.code }))}
					on:change={(e) => dat({ nhom: e.detail, loai: '', file: null, luc: '' })}
				/>
			{/if}
		</div>
		<div class="field">
			<span class="lbl">Năm dữ liệu <span class="req">*</span></span>
			{#if dangKT}
				<div class="ro lk"><Icon name="lock" size={13} />{n.nam}</div>
			{:else}
				<Dropdown
					value={n.nam}
					placeholder="Chọn năm"
					title="Năm của số liệu trong tệp"
					options={DP_NAM.map((y) => ({ v: y, t: y }))}
					on:change={(e) => dat({ nam: e.detail })}
				/>
			{/if}
		</div>
		{#if nhieuLoai}
			<div class="field s3">
				<span class="lbl">Loại tệp <span class="req">*</span></span>
				{#if dangKT}
					<div class="ro lk"><Icon name="lock" size={13} />{loai?.ten}</div>
				{:else}
					<Dropdown
						value={n.loai}
						placeholder="Chọn loại tệp"
						title="Loại tệp"
						options={(dom?.loai_tep ?? []).map((l) => ({ v: l.ma, t: l.ten, phu: l.phu }))}
						on:change={(e) => dat({ loai: e.detail, file: null, luc: '' })}
					/>
				{/if}
			</div>
		{/if}
	</div>
</section>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<section
	class="card"
	class:over={keo}
	on:dragover|preventDefault={() => (keo = !khoaTep)}
	on:dragleave={() => (keo = false)}
	on:drop|preventDefault={(e) => {
		keo = false;
		chonTep(e.dataTransfer?.files?.[0]);
	}}
>
	<div class="card-h">
		<div>
			<h2>File đính kèm</h2>
			<div class="sub">{n.file ? 1 : 0}/1 File</div>
		</div>
	</div>
	<div class="tw">
		<div class="tbox">
			<table>
				<thead>
					<tr>
						<th>Loại file</th><th>Tên tài liệu</th><th class="r">Dung lượng</th><th>Người upload</th><th>Ngày upload</th><th>Trạng thái</th><th></th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td class="s">{nhieuLoai ? (n.loai ? (loai?.ten ?? '') : '') : (loai?.ten ?? $dpDomains[0]?.loai_tep?.[0]?.ten ?? '')}</td>
						<td class="s" style="word-break:break-all">{n.file?.name ?? ''}</td>
						<td class="r">{n.file ? kb(n.file.size) : '0,0 KB'}</td>
						<td>{n.file ? ($user?.name ?? '') : ''}</td>
						<td>{n.file ? n.luc : '-'}</td>
						<td>
							{#if !n.file}<Badge t="Chưa upload" k="muted" />
							{:else if hopLe}<Badge t="Đã chọn · hợp lệ" k="ok" />
							{:else}<Badge t="Không phải tệp .xlsx" k="err" />{/if}
						</td>
						<td>
							<div class="row" style="gap:6px;flex-wrap:nowrap;justify-content:flex-end">
								<label
									class="iconbtn"
									class:off={khoaTep}
									title={thieuNN ? `${thieuNN} trước khi chọn tệp` : 'Chọn tệp từ máy'}
									aria-disabled={khoaTep}
									style="cursor:{khoaTep ? 'not-allowed' : 'pointer'}"
								>
									<Icon name="up" size={16} /><span class="sr">Chọn tệp</span>
									<input
										type="file"
										accept=".xlsx,.xls"
										hidden
										disabled={khoaTep}
										on:change={(e) => {
											chonTep(e.currentTarget.files?.[0]);
											e.currentTarget.value = '';
										}}
									/>
								</label>
								<button
									type="button"
									class="iconbtn"
									disabled={!n.file || dangKT}
									title="Tải tệp đã chọn về máy"
									aria-label="Tải tệp đã chọn về máy"
									on:click={() => n.file && luuTep(n.file, n.file.name)}><Icon name="down" size={16} /></button
								>
								<button
									type="button"
									class="iconbtn"
									disabled={!n.file || dangKT}
									title="Bỏ tệp đã chọn"
									aria-label="Bỏ tệp đã chọn"
									on:click={() => dat({ file: null, luc: '' })}><Icon name="trash" size={16} /></button
								>
							</div>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		{#if thieuNN && !n.file}
			<p class="hint" style="margin:10px 0 0"><Icon name="lock" size={12} /> {thieuNN} ở thẻ phía trên trước, rồi mới chọn được tệp.</p>
		{/if}
	</div>
</section>
