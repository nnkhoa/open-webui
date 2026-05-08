<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { pendingMessageFromSidebar } from '$lib/stores';
	import { getSidebarHeartbeat, getSidebarSignals } from '$lib/apis/ai4bi';

	type SignalItem = {
		id: number;
		type: 'critical' | 'watch' | 'positive';
		title: string;
		desc: string;
	};

	type HeartbeatItem = {
		id: number;
		label: string;
		value: string;
		delta: string;
		trend: 'up' | 'down' | 'neutral';
	};

	const SIGNALS_FETCH_LIMIT = 5;
	const SIGNALS_INITIAL_VISIBLE = 3;
	const HEARTBEAT_FETCH_LIMIT = 8;
	const HEARTBEAT_INITIAL_VISIBLE = 4;
	const LOAD_MORE_FETCH_LIMIT = 12;

	let activeSignalId: number | null = null;
	let signalItems: SignalItem[] = [];
	let heartbeatItems: HeartbeatItem[] = [];

	let signalsStatus: 'idle' | 'loading' | 'ready' | 'error' = 'idle';
	let heartbeatStatus: 'idle' | 'loading' | 'ready' | 'error' = 'idle';

	let signalsLoading = false;
	let heartbeatLoading = false;
	let signalsExpanded = false;
	let heartbeatExpanded = false;
	let signalsOffset = 0;
	let heartbeatOffset = 0;
	let signalsHasMore = false;
	let heartbeatHasMore = false;
	let signalsError = '';
	let heartbeatError = '';
	let signalsGenerating = false;
	let heartbeatGenerating = false;

	// Polling: when backend signals "isGenerating", poll every 3s until data appears
	// or until the user navigates away. Cap total polling at ~3 minutes as a safety net.
	const POLL_INTERVAL_MS = 3000;
	const POLL_MAX_ATTEMPTS = 60;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let pollAttempts = 0;

	const signalMeta = {
		critical: { dot: '#E24B4A', tag: 'Cần xử lý', tagBg: 'rgba(226, 75, 74, 0.14)' },
		watch: { dot: '#D97706', tag: 'Theo dõi', tagBg: 'rgba(217, 119, 6, 0.14)' },
		positive: { dot: '#1D9E75', tag: 'Tích cực', tagBg: 'rgba(29, 158, 117, 0.14)' }
	};

	function formatCount(value: number) {
		if (!Number.isFinite(value)) return '';
		if (value > 99) return '99+';
		return String(value);
	}

	function getToken() {
		return localStorage.token ?? '';
	}

	async function loadSignals(reset = false) {
		if (signalsLoading) return;
		signalsLoading = true;
		signalsError = '';

		if (reset) {
			signalsStatus = 'loading';
			signalsOffset = 0;
			signalsHasMore = false;
			signalItems = [];
		}

		try {
			const offset = reset ? 0 : signalsOffset;
			const limit = reset ? SIGNALS_FETCH_LIMIT : LOAD_MORE_FETCH_LIMIT;
			const data = await getSidebarSignals(getToken(), { limit, offset });

			if (data?.isConfigured === false) {
				signalsStatus = 'ready';
				signalsError = data?.error || 'Chưa có thông tin.';
				signalItems = [];
				signalsHasMore = false;
				signalsOffset = 0;
				signalsGenerating = false;
				return;
			}

			const incoming = Array.isArray(data?.items) ? data.items : [];
			signalItems = reset ? incoming : [...signalItems, ...incoming];
			signalsOffset = typeof data?.nextOffset === 'number' ? data.nextOffset : signalItems.length;
			signalsHasMore = Boolean(data?.hasMore);
			signalsGenerating = Boolean(data?.isGenerating);
			signalsStatus = 'ready';
		} catch (error: unknown) {
			const resolvedError = error as { detail?: string; message?: string };
			signalsStatus = 'error';
			signalsError = resolvedError?.detail || resolvedError?.message || 'Không tải được tín hiệu.';
			signalsGenerating = false;
		} finally {
			signalsLoading = false;
		}
	}

	async function loadHeartbeat(reset = false) {
		if (heartbeatLoading) return;
		heartbeatLoading = true;
		heartbeatError = '';

		if (reset) {
			heartbeatStatus = 'loading';
			heartbeatOffset = 0;
			heartbeatHasMore = false;
			heartbeatItems = [];
		}

		try {
			const offset = reset ? 0 : heartbeatOffset;
			const limit = reset ? HEARTBEAT_FETCH_LIMIT : LOAD_MORE_FETCH_LIMIT;
			const data = await getSidebarHeartbeat(getToken(), { limit, offset });

			if (data?.isConfigured === false) {
				heartbeatStatus = 'ready';
				heartbeatError = data?.error || 'Chưa có thông tin.';
				heartbeatItems = [];
				heartbeatHasMore = false;
				heartbeatOffset = 0;
				heartbeatGenerating = false;
				return;
			}

			const incoming = Array.isArray(data?.items) ? data.items : [];
			heartbeatItems = reset ? incoming : [...heartbeatItems, ...incoming];
			heartbeatOffset =
				typeof data?.nextOffset === 'number' ? data.nextOffset : heartbeatItems.length;
			heartbeatHasMore = Boolean(data?.hasMore);
			heartbeatGenerating = Boolean(data?.isGenerating);
			heartbeatStatus = 'ready';
		} catch (error: unknown) {
			const resolvedError = error as { detail?: string; message?: string };
			heartbeatStatus = 'error';
			heartbeatError =
				resolvedError?.detail || resolvedError?.message || 'Không tải được nhịp đập.';
			heartbeatGenerating = false;
		} finally {
			heartbeatLoading = false;
		}
	}

	function stopPolling() {
		if (pollTimer !== null) {
			clearTimeout(pollTimer);
			pollTimer = null;
		}
		pollAttempts = 0;
	}

	function ensurePolling() {
		// Re-poll only while at least one section is generating with no data yet,
		// and we haven't blown the safety cap.
		const stillGenerating =
			(signalItems.length === 0 && signalsGenerating) ||
			(heartbeatItems.length === 0 && heartbeatGenerating);

		if (!stillGenerating || pollAttempts >= POLL_MAX_ATTEMPTS) {
			stopPolling();
			return;
		}

		if (pollTimer !== null) return; // already scheduled
		pollTimer = setTimeout(async () => {
			pollTimer = null;
			pollAttempts += 1;
			await Promise.all([
				signalItems.length === 0 ? loadSignals(true) : Promise.resolve(),
				heartbeatItems.length === 0 ? loadHeartbeat(true) : Promise.resolve()
			]);
			ensurePolling();
		}, POLL_INTERVAL_MS);
	}

	$: if (signalsStatus === 'ready' || heartbeatStatus === 'ready') {
		// React to status changes — schedule a follow-up poll if backend is still generating.
		ensurePolling();
	}

	$: visibleSignals = signalItems.slice(0, SIGNALS_INITIAL_VISIBLE);
	$: visibleHeartbeat = heartbeatExpanded
		? heartbeatItems
		: heartbeatItems.slice(0, HEARTBEAT_INITIAL_VISIBLE);
	$: signalsCanExpand = signalItems.length > SIGNALS_INITIAL_VISIBLE || signalsHasMore;
	$: heartbeatCanExpand = heartbeatItems.length > HEARTBEAT_INITIAL_VISIBLE || heartbeatHasMore;

	onMount(async () => {
		await Promise.all([loadSignals(true), loadHeartbeat(true)]);
	});

	onDestroy(() => {
		stopPolling();
	});

	function handleSignalClick(item: SignalItem) {
		activeSignalId = item.id;
		// Ask a follow-up question (avoid copying the sidebar text verbatim).
		const question = `Phân tích sâu hơn về tín hiệu "${item.title}". Nêu nguyên nhân chính, drill-down theo các chiều quan trọng, và đề xuất hành động ưu tiên.`;
		pendingMessageFromSidebar.set(question);
	}

	function handleHeartbeatClick(item: HeartbeatItem) {
		// Ask a follow-up question (avoid copying the sidebar card verbatim).
		const question = `Giải thích KPI "${item.label}" hiện tại ${item.value}. So sánh với kỳ trước, tìm nguyên nhân biến động và gợi ý các hướng drill-down phù hợp.`;
		pendingMessageFromSidebar.set(question);
	}
</script>

<section class="ai4bi-shell">
	<div class="ai4bi-container">
		<div class="signals-section">
			<div class="section-head">
				<div class="badge">
					<span>Tín hiệu</span>
					{#if signalItems.length > 0}
						<span class="count">{formatCount(signalItems.length)}</span>
					{/if}
				</div>
			</div>

			<div class="signals-list">
				{#if signalsStatus === 'loading' && signalItems.length === 0}
					<div class="hint">Đang tải...</div>
				{:else if signalItems.length === 0 && signalsGenerating}
					<div class="hint">Đang chuẩn bị thông tin</div>
				{:else if signalItems.length === 0}
					<div class="hint">{signalsError || 'Chưa có thông tin.'}</div>
				{/if}

				{#each visibleSignals as item}
					<button
						class="signal-card"
						class:active={activeSignalId === item.id}
						type="button"
						on:click={() => handleSignalClick(item)}
					>
						<div class="signal-row">
							<div class="dot" style={`background:${signalMeta[item.type].dot};`}></div>
							<div class="signal-content">
								<p class="signal-title">{item.title}</p>
								<p class="signal-desc">{item.desc}</p>
								<div class="tag-row">
									<span
										class="tag"
										style={`background:${signalMeta[item.type].tagBg}; color:${signalMeta[item.type].dot};`}
									>
										{signalMeta[item.type].tag}
									</span>
								</div>
							</div>
						</div>
					</button>
				{/each}
			</div>

		</div>

		<div class="heartbeat-section">
			<div class="heartbeat-block">
				<p class="heartbeat-title">Nhịp đập</p>

				{#if heartbeatStatus === 'loading' && heartbeatItems.length === 0}
					<div class="hint compact">Đang tải...</div>
				{:else if heartbeatItems.length === 0 && heartbeatGenerating}
					<div class="hint compact">Đang chuẩn bị thông tin</div>
				{:else if heartbeatItems.length === 0}
					<div class="hint compact">{heartbeatError || 'Chưa có thông tin.'}</div>
				{/if}

				<div class="heartbeat-grid">
					{#each visibleHeartbeat as item}
						<button class="heartbeat-card" type="button" on:click={() => handleHeartbeatClick(item)}>
							<p class="heartbeat-label">{item.label}</p>
							<div class="heartbeat-value-row">
								<span class="heartbeat-value">{item.value}</span>
								{#if item.delta}
									<span
										class="heartbeat-delta"
										class:up={item.trend === 'up'}
										class:down={item.trend === 'down'}
									>
										{item.delta}
									</span>
								{/if}
							</div>
						</button>
					{/each}
				</div>

				{#if heartbeatItems.length > 0}
					<div class="footer-actions heartbeat-footer">
						{#if heartbeatLoading}
							<span class="footer-note">Đang tải...</span>
						{:else if heartbeatExpanded}
							<button class="ghost-button" type="button" on:click={() => (heartbeatExpanded = false)}>
								Ẩn bớt
							</button>
						{:else if heartbeatCanExpand}
							<button
								class="ghost-button"
								type="button"
								on:click={async () => {
									if (heartbeatHasMore) {
										await loadHeartbeat(false);
									}
									heartbeatExpanded = true;
								}}
							>
								Xem thêm
							</button>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	</div>
</section>

<style>
	.ai4bi-shell {
		display: flex;
		flex-direction: column;
		height: 100%;
		padding: 0.5rem;
	}

	.ai4bi-container {
		display: flex;
		flex-direction: column;
		height: 100%;
		gap: 1rem;
	}

	.signals-section {
		flex: 0 0 60%;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
	}

	.heartbeat-section {
		flex: 0 0 40%;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
	}

	.section-head {
		padding: 0.25rem 0.75rem 0.5rem;
		flex-shrink: 0;
	}

	.badge {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border-radius: 999px;
		background: #19226d;
		color: #fff;
		font-size: 11px;
		font-weight: 700;
		padding: 0.25rem 0.7rem;
	}

	.count {
		font-size: 10px;
		opacity: 0.78;
	}

	.signals-list {
		flex: 1;
		overflow-y: auto;
		overflow-x: hidden;
		padding: 0 0.4rem;
		min-height: 0;
	}

	/* Scrollbar styling */
	.signals-list::-webkit-scrollbar {
		width: 4px;
	}

	.signals-list::-webkit-scrollbar-track {
		background: transparent;
	}

	.signals-list::-webkit-scrollbar-thumb {
		background: transparent;
		border-radius: 2px;
	}

	.signals-list:hover::-webkit-scrollbar-thumb {
		background: rgba(148, 163, 184, 0.3);
	}

	.signals-list::-webkit-scrollbar-thumb:hover {
		background: rgba(148, 163, 184, 0.5);
	}

	.hint {
		padding: 0.25rem 0.6rem 0.6rem;
		color: #64748b;
		font-size: 12px;
		line-height: 1.45;
	}

	.compact {
		padding-inline: 0.1rem;
	}

	.signal-card {
		width: 100%;
		margin-bottom: 0.35rem;
		border: 0;
		border-left: 3px solid transparent;
		border-radius: 1rem;
		background: transparent;
		padding: 0.75rem;
		text-align: left;
		transition:
			background 160ms ease,
			border-color 160ms ease;
		flex-shrink: 0;
		cursor: pointer;
	}

	.signal-card:hover {
		background: rgba(248, 250, 252, 0.9);
	}

	.signal-card.active {
		border-left-color: #19226d;
		background: rgba(232, 234, 245, 0.95);
	}

	.signal-row {
		display: flex;
		align-items: flex-start;
		gap: 0.625rem;
	}

	.dot {
		width: 9px;
		height: 9px;
		flex-shrink: 0;
		border-radius: 50%;
		margin-top: 4px;
	}

	.signal-content {
		min-width: 0;
		flex: 1;
	}

	.signal-title {
		display: -webkit-box;
		overflow: hidden;
		margin: 0 0 0.25rem;
		color: #0f172a;
		font-size: 12px;
		font-weight: 700;
		line-height: 1.45;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		min-height: 35px;
	}

	.signal-desc {
		display: -webkit-box;
		overflow: hidden;
		margin: 0;
		color: #475569;
		font-size: 11px;
		line-height: 1.5;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		min-height: 33px;
	}

	.tag-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.tag {
		display: inline-flex;
		border-radius: 0.5rem;
		font-size: 10px;
		font-weight: 700;
		padding: 0.12rem 0.45rem;
	}

	.footer-actions {
		display: flex;
		justify-content: center;
		padding-top: 0.15rem;
		flex-shrink: 0;
	}

	.footer-note {
		color: #64748b;
		font-size: 12px;
		font-weight: 600;
	}

	.ghost-button {
		border: 0;
		border-radius: 0.75rem;
		background: transparent;
		padding: 0.5rem 0.9rem;
		color: #475569;
		font-size: 12px;
		font-weight: 700;
	}

	.ghost-button:hover {
		background: rgba(248, 250, 252, 0.95);
	}

	.heartbeat-block {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		overflow: hidden;
		border-top: 1px solid rgba(226, 232, 240, 0.8);
		padding: 1rem 0.75rem 0;
	}

	.heartbeat-title {
		margin: 0 0 0.75rem;
		color: #475569;
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.02em;
		flex-shrink: 0;
	}

	.heartbeat-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem;
		flex: 1;
		overflow-y: auto;
		min-height: 0;
		padding-right: 2px;
	}

	/* Scrollbar for heartbeat */
	.heartbeat-grid::-webkit-scrollbar {
		width: 4px;
	}

	.heartbeat-grid::-webkit-scrollbar-track {
		background: transparent;
	}

	.heartbeat-grid::-webkit-scrollbar-thumb {
		background: transparent;
		border-radius: 2px;
	}

	.heartbeat-grid:hover::-webkit-scrollbar-thumb {
		background: rgba(148, 163, 184, 0.3);
	}

	.heartbeat-grid::-webkit-scrollbar-thumb:hover {
		background: rgba(148, 163, 184, 0.5);
	}

	.heartbeat-card {
		display: flex;
		min-height: 92px;
		max-height: 92px;
		width: 100%;
		flex-direction: column;
		justify-content: space-between;
		border: 0;
		border-radius: 1rem;
		background: #f8fafc;
		padding: 0.7rem;
		text-align: left;
		flex-shrink: 0;
		cursor: pointer;
	}

	.heartbeat-card:hover {
		background: #e2e8f0;
	}

	.heartbeat-label {
		margin: 0;
		color: #475569;
		font-size: 11px;
		line-height: 1.45;
	}

	.heartbeat-value-row {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.3rem;
	}

	.heartbeat-value {
		max-width: 100%;
		word-break: break-word;
		color: #0f172a;
		font-size: 22px;
		font-weight: 700;
		line-height: 1;
	}

	.heartbeat-delta {
		font-size: 11px;
		font-weight: 700;
		line-height: 1.4;
	}

	.heartbeat-delta.up {
		color: #1d9e75;
	}

	.heartbeat-delta.down {
		color: #e24b4a;
	}
</style>
