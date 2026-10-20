<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import {
		DataPortalApiError,
		deleteDbConfig,
		getDbConfig,
		testDbConfig,
		updateDbConfig
	} from '$lib/apis/data-portal';
	import type { DbConfig, DbConfigForm } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Dialog from '$lib/components/data-portal/Dialog.svelte';
	import { formatDateTime } from '$lib/components/data-portal/format';
	import { refreshPortalStatus } from '$lib/stores/dataPortal';

	const i18n: Writable<i18nType> = getContext('i18n');

	type Notice = { tone: 'ok' | 'err' | 'info'; text: string };

	let dbConfig: DbConfig | null = null;
	let form = { host: '', port: '', database: '', username: '', password: '', note: '' };
	let showPassword = false;
	let fieldErrors: Record<string, string> = {};
	let notice: Notice | null = null;
	let successMessage = '';
	let confirmingDelete = false;
	let busy = false;

	const loadConfig = async () => {
		dbConfig = await getDbConfig(localStorage.token);
		await refreshPortalStatus();
		const config = dbConfig?.config;
		form = {
			host: config?.host ?? '',
			port: config?.port ? String(config.port) : '',
			database: config?.database ?? '',
			username: config?.username ?? '',
			password: '',
			note: config?.note ?? ''
		};
	};

	onMount(() =>
		loadConfig().catch((error) => (notice = { tone: 'err', text: (error as Error).message }))
	);

	const validateForm = () => {
		const errors: Record<string, string> = {};
		const port = form.port.trim();
		if (!form.host.trim()) errors.host = $i18n.t('Server address is required.');
		if (!port) errors.port = $i18n.t('Port is required.');
		else if (!/^\d+$/.test(port)) errors.port = $i18n.t('Port must be a number.');
		else if (+form.port < 1 || +form.port > 65535)
			errors.port = $i18n.t('Port must be between 1 and 65535.');
		if (!form.database.trim()) errors.database = $i18n.t('Database name is required.');
		if (!form.username.trim()) errors.username = $i18n.t('Username is required.');
		fieldErrors = errors;
		return !Object.keys(errors).length;
	};

	const formData = (): DbConfigForm => ({
		host: form.host.trim(),
		port: Number(form.port),
		database: form.database.trim(),
		username: form.username.trim(),
		password: form.password,
		note: form.note.trim()
	});

	const showError = (error: unknown) => {
		if (error instanceof DataPortalApiError && error.fieldErrors) {
			fieldErrors = error.fieldErrors;
			notice = null;
		} else {
			notice = { tone: 'err', text: (error as Error).message };
		}
	};

	const testConnection = async () => {
		successMessage = '';
		if (!validateForm()) return;
		busy = true;
		notice = { tone: 'info', text: $i18n.t('Testing connection…') };
		try {
			const result = await testDbConfig(localStorage.token, formData());
			notice = { tone: result?.ok ? 'ok' : 'err', text: result?.message ?? '' };
		} catch (error) {
			showError(error);
		} finally {
			busy = false;
		}
	};

	const saveConfig = async () => {
		successMessage = '';
		if (!validateForm()) return;
		busy = true;
		notice = { tone: 'info', text: $i18n.t('Testing connection…') };
		try {
			const result = await updateDbConfig(localStorage.token, formData());
			if (result?.ok) {
				notice = null;
				successMessage = result.message;
				await loadConfig();
			} else {
				notice = { tone: 'err', text: result?.message ?? '' };
			}
		} catch (error) {
			showError(error);
		} finally {
			busy = false;
		}
	};

	const removeConfig = async () => {
		confirmingDelete = false;
		try {
			const result = await deleteDbConfig(localStorage.token);
			notice = null;
			successMessage =
				result?.message ?? $i18n.t('Configuration removed. Data in that database was not touched.');
			await loadConfig();
		} catch (error) {
			notice = { tone: 'err', text: (error as Error).message };
		}
	};
</script>

<HeaderCard title={$i18n.t('Database configuration')}>
	<svelte:fragment slot="actions">
		<button
			type="button"
			class="btn"
			disabled={busy}
			title={$i18n.t('Try connecting to the server with the entered details. Nothing is saved.')}
			on:click={testConnection}>{$i18n.t('Test connection')}</button
		>
		<button
			type="button"
			class="btn primary"
			disabled={busy}
			title={$i18n.t(
				'Try connecting; if it works, save it and Data Portal uses this connection right away'
			)}
			on:click={saveConfig}>{$i18n.t('Save and reconnect')}</button
		>
	</svelte:fragment>
</HeaderCard>

{#if successMessage}<Banner tone="ok" icon="check" title={successMessage} />{/if}

{#if dbConfig && !dbConfig.config}
	<Banner
		tone="warn"
		title={$i18n.t(
			'No database is configured. Data Portal stays locked until a connection is saved here.'
		)}
	/>
{/if}

{#if dbConfig?.connection}
	<section class="card">
		<div class="conn">
			<span class="dot" style={dbConfig.connection.ok ? '' : 'background:var(--err)'}></span>
			<div>
				<b>{dbConfig.connection.ok ? $i18n.t('Currently connected') : $i18n.t('Not connected')}</b>
				<div class="hint" style="margin:2px 0 0">{dbConfig.connection.description}</div>
			</div>
		</div>
	</section>
{/if}

{#if notice}
	<Banner
		tone={notice.tone}
		icon={notice.tone === 'ok' ? 'check' : notice.tone === 'err' ? 'x' : 'info'}
		title={notice.text}
	/>
{/if}

<form class="card" on:submit|preventDefault={saveConfig}>
	<div class="card-h">
		<div>
			<h2>{$i18n.t('Connection details')}</h2>
			<div class="sub">
				{$i18n.t('Please fill in the details below; fields marked')} (<span style="color:var(--req)"
					>*</span
				>) {$i18n.t('are required.')}
			</div>
		</div>
	</div>
	<div class="form-grid">
		<div class="field">
			<label for="host">{$i18n.t('Server')} <span class="req">*</span></label>
			<input id="host" class="inp" placeholder="localhost" bind:value={form.host} />
			{#if fieldErrors.host}<div class="hint err">{fieldErrors.host}</div>{/if}
		</div>
		<div class="field">
			<label for="port">{$i18n.t('Port')} <span class="req">*</span></label>
			<input id="port" class="inp" inputmode="numeric" bind:value={form.port} />
			{#if fieldErrors.port}<div class="hint err">{fieldErrors.port}</div>{/if}
		</div>
		<div class="field">
			<label for="database">{$i18n.t('Database name')} <span class="req">*</span></label>
			<input id="database" class="inp" placeholder="aibi_database" bind:value={form.database} />
			{#if fieldErrors.database}<div class="hint err">{fieldErrors.database}</div>{/if}
		</div>
		<div class="field">
			<label for="username">{$i18n.t('Username')} <span class="req">*</span></label>
			<input id="username" class="inp" autocomplete="off" bind:value={form.username} />
			{#if fieldErrors.username}<div class="hint err">{fieldErrors.username}</div>{/if}
		</div>
		<div class="field s2">
			<label for="password">{$i18n.t('Password')}</label>
			<div class="row" style="flex-wrap:nowrap">
				{#if showPassword}
					<input
						id="password"
						class="inp"
						type="text"
						autocomplete="new-password"
						bind:value={form.password}
					/>
				{:else}
					<input
						id="password"
						class="inp"
						type="password"
						autocomplete="new-password"
						bind:value={form.password}
					/>
				{/if}
				<button
					type="button"
					class="btn"
					aria-pressed={showPassword}
					aria-controls="password"
					on:click={() => (showPassword = !showPassword)}
					>{showPassword ? $i18n.t('Hide password') : $i18n.t('Show password')}</button
				>
			</div>
			<div class="hint">{$i18n.t('Leave empty to keep the saved password.')}</div>
		</div>
		<div class="field s3">
			<label for="note">{$i18n.t('Connection note')}</label>
			<input
				id="note"
				class="inp"
				placeholder={$i18n.t('For example: postgres container on the internal server')}
				bind:value={form.note}
			/>
		</div>
		<div class="s3 helps">
			<p class="guide">
				<b>{$i18n.t('Test connection')}</b> — {$i18n.t(
					'try connecting to the server with the entered details. Nothing is saved.'
				)}
			</p>
			<p class="guide">
				<b>{$i18n.t('Save and reconnect')}</b> — {$i18n.t(
					'try connecting; if it works, save it and Data Portal uses this connection right away. If not, show the error and keep the old configuration.'
				)}
			</p>
		</div>
	</div>
</form>

{#if dbConfig?.config}
	<section
		class="card"
		style="padding:18px 24px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap"
	>
		<dl class="kv">
			<dt>{$i18n.t('Last test')}</dt>
			<dd>{formatDateTime(dbConfig.last_tested_at)}</dd>
			<dt>{$i18n.t('Configuration saved at')}</dt>
			<dd>{formatDateTime(dbConfig.saved_at)}</dd>
		</dl>
		<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
			<button type="button" class="btn danger" on:click={() => (confirmingDelete = true)}
				>{$i18n.t('Remove configuration')}</button
			>
			<span class="hint" style="margin:0"
				>{$i18n.t('Deletes the saved configuration. Data in the database is not touched.')}</span
			>
		</div>
	</section>
{/if}

{#if confirmingDelete}
	<Dialog label={$i18n.t('Remove configuration')} on:close={() => (confirmingDelete = false)}>
		<h2>{$i18n.t('Remove configuration')}</h2>
		<p>{$i18n.t('Remove the connection configuration? Data in that database is not touched.')}</p>
		<div class="row" style="justify-content:flex-end;margin-top:4px">
			<button type="button" class="btn" on:click={() => (confirmingDelete = false)}
				>{$i18n.t('Dismiss')}</button
			>
			<button type="button" class="btn danger-solid" on:click={removeConfig}
				>{$i18n.t('Remove configuration')}</button
			>
		</div>
	</Dialog>
{/if}
