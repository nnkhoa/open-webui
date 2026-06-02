<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { models } from '$lib/stores';
	import { getChatUsage } from '$lib/apis/analytics';
	import { getAllChats } from '$lib/apis/chats';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	type ChatMeta = { id: string; title: string; updated_at: number };
	type ChatUsageData = {
		chat_id: string;
		total_input_tokens: number;
		total_output_tokens: number;
		total_tokens: number;
		message_count: number;
		by_model: Record<
			string,
			{ input_tokens: number; output_tokens: number; total_tokens: number; message_count: number }
		>;
		messages: Array<{
			message_id: string;
			role: string;
			model_id: string | null;
			input_tokens: number;
			output_tokens: number;
			total_tokens: number;
			created_at: number;
		}>;
	};

	let chats: ChatMeta[] = [];
	let selectedChatId: string = '';
	let usage: ChatUsageData | null = null;
	let loadingChats = true;
	let loadingUsage = false;

	const formatNumber = (n: number) => n.toLocaleString();
	const formatDate = (ts: number) => new Date(ts * 1000).toLocaleString();
	const modelName = (id: string | null) => {
		if (!id) return '—';
		const m = $models.find((x) => x.id === id);
		return m?.name || id;
	};

	const loadChats = async () => {
		loadingChats = true;
		try {
			const list = await getAllChats(localStorage.token);
			chats = (list || []).slice(0, 100).map((c: any) => ({
				id: c.id,
				title: c.title || '(untitled)',
				updated_at: c.updated_at
			}));
			if (chats.length && !selectedChatId) {
				selectedChatId = chats[0].id;
			}
		} catch (err) {
			console.error('Load chats failed:', err);
		}
		loadingChats = false;
	};

	const loadUsage = async () => {
		if (!selectedChatId) return;
		loadingUsage = true;
		try {
			usage = await getChatUsage(localStorage.token, selectedChatId);
		} catch (err) {
			console.error('Load usage failed:', err);
			usage = null;
		}
		loadingUsage = false;
	};

	$: if (selectedChatId) loadUsage();

	onMount(loadChats);
</script>

<div class="pt-0.5 pb-1 sticky top-0 z-10 bg-white dark:bg-gray-900">
	<div class="text-xl font-medium px-0.5 mb-2">{$i18n.t('Chat Usage')}</div>
	<div class="flex gap-2 items-center">
		<select
			bind:value={selectedChatId}
			class="text-sm bg-gray-50 dark:bg-gray-850 rounded-md px-3 py-1.5 w-full max-w-md outline-none border border-gray-200 dark:border-gray-700"
			disabled={loadingChats}
		>
			{#if loadingChats}
				<option>{$i18n.t('Loading')}…</option>
			{:else if !chats.length}
				<option>{$i18n.t('No chats')}</option>
			{:else}
				{#each chats as c}
					<option value={c.id}>{c.title}</option>
				{/each}
			{/if}
		</select>
	</div>
</div>

<div class="mt-4 min-h-[100px] relative">
	{#if loadingUsage}
		<div class="absolute inset-0 flex items-center justify-center z-10 bg-white/50 dark:bg-gray-900/50">
			<Spinner className="size-5" />
		</div>
	{/if}

	{#if usage}
		<!-- Summary cards -->
		<div class="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
			<div class="rounded-lg p-3 bg-gray-50 dark:bg-gray-850">
				<div class="text-xs text-gray-500">{$i18n.t('Input tokens')}</div>
				<div class="text-lg font-semibold">{formatNumber(usage.total_input_tokens)}</div>
			</div>
			<div class="rounded-lg p-3 bg-gray-50 dark:bg-gray-850">
				<div class="text-xs text-gray-500">{$i18n.t('Output tokens')}</div>
				<div class="text-lg font-semibold">{formatNumber(usage.total_output_tokens)}</div>
			</div>
			<div class="rounded-lg p-3 bg-gray-50 dark:bg-gray-850">
				<div class="text-xs text-gray-500">{$i18n.t('Total tokens')}</div>
				<div class="text-lg font-semibold">{formatNumber(usage.total_tokens)}</div>
			</div>
			<div class="rounded-lg p-3 bg-gray-50 dark:bg-gray-850">
				<div class="text-xs text-gray-500">{$i18n.t('Messages')}</div>
				<div class="text-lg font-semibold">{usage.message_count}</div>
			</div>
		</div>

		<!-- By model -->
		{#if Object.keys(usage.by_model).length}
			<div class="mb-4">
				<div class="text-sm font-medium px-0.5 mb-2">{$i18n.t('By model')}</div>
				<table class="w-full text-sm text-left text-gray-500 dark:text-gray-400">
					<thead class="text-xs text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800">
						<tr>
							<th class="px-3 py-2">{$i18n.t('Model')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Input')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Output')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Total')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Messages')}</th>
						</tr>
					</thead>
					<tbody>
						{#each Object.entries(usage.by_model) as [modelId, m]}
							<tr class="border-b border-gray-100 dark:border-gray-800">
								<td class="px-3 py-2 font-mono text-xs">{modelName(modelId)}</td>
								<td class="px-3 py-2 text-right">{formatNumber(m.input_tokens)}</td>
								<td class="px-3 py-2 text-right">{formatNumber(m.output_tokens)}</td>
								<td class="px-3 py-2 text-right font-medium">{formatNumber(m.total_tokens)}</td>
								<td class="px-3 py-2 text-right">{m.message_count}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		<!-- Per-message breakdown -->
		{#if usage.messages.length}
			<div>
				<div class="text-sm font-medium px-0.5 mb-2">{$i18n.t('Messages')}</div>
				<table class="w-full text-sm text-left text-gray-500 dark:text-gray-400">
					<thead class="text-xs text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800">
						<tr>
							<th class="px-3 py-2">{$i18n.t('Created')}</th>
							<th class="px-3 py-2">{$i18n.t('Model')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Input')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Output')}</th>
							<th class="px-3 py-2 text-right">{$i18n.t('Total')}</th>
						</tr>
					</thead>
					<tbody>
						{#each usage.messages as msg}
							<tr class="border-b border-gray-100 dark:border-gray-800">
								<td class="px-3 py-2 text-xs">{formatDate(msg.created_at)}</td>
								<td class="px-3 py-2 font-mono text-xs">{modelName(msg.model_id)}</td>
								<td class="px-3 py-2 text-right">{formatNumber(msg.input_tokens)}</td>
								<td class="px-3 py-2 text-right">{formatNumber(msg.output_tokens)}</td>
								<td class="px-3 py-2 text-right font-medium">{formatNumber(msg.total_tokens)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{:else if !loadingUsage && selectedChatId}
		<div class="text-center text-xs text-gray-500 py-4">
			{$i18n.t('No usage data for this chat')}
		</div>
	{/if}
</div>
