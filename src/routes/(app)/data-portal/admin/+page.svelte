<script lang="ts">
	// Cấu hình database — chỉ Admin (đặc tả mục 20).
	import { onMount } from 'svelte';
	import { dpGet, dpSend, DpError } from '$lib/apis/data-portal';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Dialog from '$lib/components/data-portal/Dialog.svelte';
	import { thoiGian } from '$lib/components/data-portal/fmt';

	type CauHinh = {
		cau_hinh: { host: string; port: number; database: string; username: string; ghi_chu?: string } | null;
		ket_noi: { ok: boolean; mo_ta: string } | null;
		lan_thu: string | null;
		luu_luc: string | null;
	};

	let du: CauHinh | null = null;
	let f = { host: '', port: '', database: '', username: '', password: '', ghi_chu: '' };
	let hien = false;
	let loi: Record<string, string> = {};
	let kq: { k: 'ok' | 'err' | 'info'; t: string } | null = null;
	let tb = '';
	let hoiBo = false;
	let ban = false;

	const tai = async () => {
		du = await dpGet<CauHinh>('db-config');
		const c = du?.cau_hinh;
		f = {
			host: c?.host ?? '',
			port: c?.port ? String(c.port) : '',
			database: c?.database ?? '',
			username: c?.username ?? '',
			password: '',
			ghi_chu: c?.ghi_chu ?? ''
		};
	};
	onMount(() => tai().catch((e) => (kq = { k: 'err', t: (e as Error).message })));

	const kiemONhap = () => {
		const l: Record<string, string> = {};
		if (!f.host.trim()) l.host = 'Chưa nhập địa chỉ máy chủ.';
		if (!f.port.trim()) l.port = 'Chưa nhập cổng.';
		else if (!/^\d+$/.test(f.port.trim())) l.port = 'Cổng phải là số.';
		else if (+f.port < 1 || +f.port > 65535) l.port = 'Cổng phải nằm trong khoảng 1–65535.';
		if (!f.database.trim()) l.database = 'Chưa nhập tên cơ sở dữ liệu.';
		if (!f.username.trim()) l.username = 'Chưa nhập tên đăng nhập.';
		loi = l;
		return !Object.keys(l).length;
	};
	const than = () => ({
		host: f.host.trim(),
		port: Number(f.port),
		database: f.database.trim(),
		username: f.username.trim(),
		password: f.password,
		ghi_chu: f.ghi_chu.trim()
	});

	const thu = async () => {
		tb = '';
		if (!kiemONhap()) return;
		ban = true;
		kq = { k: 'info', t: 'Đang thử kết nối…' };
		try {
			const r = await dpSend<{ ok: boolean; thong_bao: string }>('POST', 'db-config/test', than());
			kq = { k: r?.ok ? 'ok' : 'err', t: r?.thong_bao ?? '' };
		} catch (e) {
			if (e instanceof DpError && e.body?.theo_o) {
				loi = e.body.theo_o;
				kq = null;
			} else kq = { k: 'err', t: e instanceof DpError ? e.message : String(e) };
		} finally {
			ban = false;
		}
	};
	const luu = async () => {
		tb = '';
		if (!kiemONhap()) return;
		ban = true;
		kq = { k: 'info', t: 'Đang thử kết nối…' };
		try {
			const r = await dpSend<{ ok: boolean; thong_bao: string }>('PUT', 'db-config', than());
			if (r?.ok) {
				kq = null;
				tb = r.thong_bao;
				await tai();
			} else kq = { k: 'err', t: r?.thong_bao ?? '' };
		} catch (e) {
			if (e instanceof DpError && e.body?.theo_o) {
				loi = e.body.theo_o;
				kq = null;
			} else kq = { k: 'err', t: e instanceof DpError ? e.message : String(e) };
		} finally {
			ban = false;
		}
	};
	const bo = async () => {
		hoiBo = false;
		try {
			const r = await dpSend<{ thong_bao: string }>('DELETE', 'db-config');
			kq = null;
			tb = r?.thong_bao ?? 'Đã bỏ cấu hình. Dữ liệu trong cơ sở dữ liệu đó không bị đụng tới.';
			await tai();
		} catch (e) {
			kq = { k: 'err', t: e instanceof DpError ? e.message : String(e) };
		}
	};
</script>

<HeaderCard title="Cấu hình database">
	<svelte:fragment slot="actions">
		<button type="button" class="btn" disabled={ban} title="Thử nối tới máy chủ với thông tin đang nhập. Không lưu gì." on:click={thu}>Kiểm tra kết nối</button>
		<button type="button" class="btn primary" disabled={ban} title="Thử nối, được thì lưu và portal dùng kết nối này ngay" on:click={luu}>Lưu và nối lại</button>
	</svelte:fragment>
</HeaderCard>

{#if tb}<Banner k="ok" icon="check" title={tb} />{/if}

{#if du?.ket_noi}
	<section class="card">
		<div class="conn">
			<span class="dot" style={du.ket_noi.ok ? '' : 'background:var(--err)'}></span>
			<div>
				<b>{du.ket_noi.ok ? 'Đang kết nối' : 'Chưa kết nối'}</b>
				<div class="hint" style="margin:2px 0 0">{du.ket_noi.mo_ta}</div>
			</div>
		</div>
	</section>
{/if}

{#if kq}<Banner k={kq.k} icon={kq.k === 'ok' ? 'check' : kq.k === 'err' ? 'x' : 'info'} title={kq.t} />{/if}

<form class="card" on:submit|preventDefault={luu}>
	<div class="card-h">
		<div>
			<h2>Thông tin kết nối</h2>
			<div class="sub">Vui lòng điền các thông tin bên dưới, thông tin có (<span style="color:var(--req)">*</span>) là bắt buộc.</div>
		</div>
	</div>
	<div class="form-grid">
		<div class="field">
			<label for="host">Máy chủ <span class="req">*</span></label>
			<input id="host" class="inp" placeholder="localhost" bind:value={f.host} />
			{#if loi.host}<div class="hint err">{loi.host}</div>{/if}
		</div>
		<div class="field">
			<label for="port">Cổng <span class="req">*</span></label>
			<input id="port" class="inp" inputmode="numeric" bind:value={f.port} />
			{#if loi.port}<div class="hint err">{loi.port}</div>{/if}
		</div>
		<div class="field">
			<label for="database">Tên cơ sở dữ liệu <span class="req">*</span></label>
			<input id="database" class="inp" placeholder="aibi_database" bind:value={f.database} />
			{#if loi.database}<div class="hint err">{loi.database}</div>{/if}
		</div>
		<div class="field">
			<label for="username">Tên đăng nhập <span class="req">*</span></label>
			<input id="username" class="inp" autocomplete="off" bind:value={f.username} />
			{#if loi.username}<div class="hint err">{loi.username}</div>{/if}
		</div>
		<div class="field s2">
			<label for="password">Mật khẩu</label>
			<div class="row" style="flex-wrap:nowrap">
				{#if hien}
					<input id="password" class="inp" type="text" autocomplete="new-password" bind:value={f.password} />
				{:else}
					<input id="password" class="inp" type="password" autocomplete="new-password" bind:value={f.password} />
				{/if}
				<button type="button" class="btn" aria-pressed={hien} aria-controls="password" on:click={() => (hien = !hien)}>{hien ? 'Ẩn' : 'Hiện'}</button>
			</div>
			<div class="hint">Để trống nghĩa là giữ mật khẩu đang lưu.</div>
		</div>
		<div class="field s3">
			<label for="ghi_chu">Ghi chú</label>
			<input id="ghi_chu" class="inp" placeholder="Ví dụ: container postgres trên máy chủ nội bộ" bind:value={f.ghi_chu} />
		</div>
		<div class="s3 helps">
			<p class="guide"><b>Kiểm tra kết nối</b> — thử nối tới máy chủ với thông tin đang nhập. Không lưu gì.</p>
			<p class="guide"><b>Lưu và nối lại</b> — thử nối, được thì lưu và portal dùng kết nối này ngay. Không được thì báo lỗi, giữ cấu hình cũ.</p>
		</div>
	</div>
</form>

{#if du?.cau_hinh}
	<section class="card" style="padding:18px 24px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">
		<dl class="kv">
			<dt>Lần thử gần nhất</dt><dd>{thoiGian(du.lan_thu)}</dd>
			<dt>Cấu hình lưu lúc</dt><dd>{thoiGian(du.luu_luc)}</dd>
		</dl>
		<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
			<button type="button" class="btn danger" on:click={() => (hoiBo = true)}>Bỏ cấu hình</button>
			<span class="hint" style="margin:0">Xoá cấu hình đã lưu. Dữ liệu trong cơ sở dữ liệu không bị đụng tới.</span>
		</div>
	</section>
{/if}

{#if hoiBo}
	<Dialog label="Bỏ cấu hình" on:close={() => (hoiBo = false)}>
		<h2>Bỏ cấu hình</h2>
		<p>Bỏ cấu hình kết nối? Dữ liệu trong cơ sở dữ liệu đó không bị đụng tới.</p>
		<div class="row" style="justify-content:flex-end;margin-top:4px">
			<button type="button" class="btn" on:click={() => (hoiBo = false)}>Huỷ</button>
			<button type="button" class="btn danger-solid" on:click={bo}>Bỏ cấu hình</button>
		</div>
	</Dialog>
{/if}
