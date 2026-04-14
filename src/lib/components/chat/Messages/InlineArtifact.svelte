
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { settings } from '$lib/stores';

	export let content: string;
	export let type: 'iframe' | 'svg' = 'iframe';

	const dispatch = createEventDispatcher();

	let iframeElement: HTMLIFrameElement;

	const iframeLoadHandler = () => {
		// Auto-resize iframe based on content
		try {
			const iframe = iframeElement;
			if (iframe && iframe.contentWindow) {
				const height = iframe.contentWindow.document.body.scrollHeight;
				iframe.style.height = height + 'px';

				// Add resize observer for dynamic content
				const resizeObserver = new iframe.contentWindow.ResizeObserver(() => {
					const newHeight = iframe.contentWindow.document.body.scrollHeight;
					iframe.style.height = newHeight + 'px';
				});
				resizeObserver.observe(iframe.contentWindow.document.body);
			}
		} catch (error) {
			console.log('[InlineArtifact] Could not auto-resize:', error);
		}

		// Block external navigation
		iframeElement?.contentWindow.addEventListener('click', function (e) {
			const target = e.target.closest('a');
			if (target && target.href) {
				e.preventDefault();
				console.info('External navigation blocked:', target.href);
			}
		}, true);
	};
</script>

<div class="inline-artifact-content">
	{#if type === 'iframe'}
		<iframe
			bind:this={iframeElement}
			title="Artifact"
			srcdoc={content}
			class="w-full border-0 rounded-lg my-3"
			style="min-height: 400px; width: 100%; overflow: hidden; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);"
			sandbox="allow-scripts allow-downloads{($settings?.iframeSandboxAllowForms ?? false) ? ' allow-forms' : ''}{($settings?.iframeSandboxAllowSameOrigin ?? false) ? ' allow-same-origin' : ''}"
			on:load={iframeLoadHandler}
		></iframe>
	{:else if type === 'svg'}
		<div class="w-full h-full flex items-center justify-center p-4 my-3">
			{@html content}
		</div>
	{/if}
</div>
