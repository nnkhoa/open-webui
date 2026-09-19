#!/usr/bin/env node
/**
 * Generates every square/wide brand icon slot from the FPT Digital wordmark.
 *
 * Source of truth: backend/open_webui/static/fpt-digital-dark.svg
 * Outputs are committed artifacts — run this manually after changing the brand
 * SVG, not as part of `npm run build`.
 *
 *   node scripts/generate-brand-icons.js            # generate
 *   node scripts/generate-brand-icons.js --measure  # re-derive crop geometry
 *
 * NOTE: replacing Open WebUI branding is permitted under LICENSE clause 4 only
 * for deployments of <=50 end users per rolling 30 days (exemption i), or with
 * written permission / an enterprise licence.
 */
import sharp from 'sharp';
import { readFile, writeFile, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC_SVG = join(ROOT, 'backend/open_webui/static/fpt-digital-dark.svg');
const TREES = [join(ROOT, 'static/static'), join(ROOT, 'backend/open_webui/static')];
const ROOT_FAVICON = join(ROOT, 'static/favicon.png');

const NAVY = '#063374'; // matches fpt-digital-dark.svg exactly
const WHITE = '#FFFFFF';

/**
 * The wordmark is one <g fill-rule="nonzero"> over two compound paths whose
 * blades overlap, so the "F" cannot be isolated by a rectangular crop alone
 * (that catches a sliver of the P blade). A parallelogram clip following the
 * blade's own slant (dx/dy ~= -0.458) isolates it without touching path data.
 * Geometry measured by rendering each subpath at 40x and scanning alpha —
 * see --measure.
 */
const F_BLADE = {
	viewBox: '0 5.8 23.1 26.4',
	x: 0,
	y: 5.8,
	w: 23.1,
	h: 26.4,
	aspect: 23.1 / 26.4,
	clip: 'M11.6 5 L23.9 5 L11.6 33 L-0.8 33 Z'
};
const SYMBOL = F_BLADE;
const LOCKUP = { w: 103, h: 38, aspect: 103 / 38 };

let PATHS = [];

const pathTags = (color) =>
	`<g clip-path="url(#c)" fill="${color}" fill-rule="nonzero">` +
	PATHS.map((d) => `<path d="${d}"/>`).join('') +
	`</g>`;

const defs = `<defs><clipPath id="c" clipPathUnits="userSpaceOnUse"><path d="${SYMBOL.clip}"/></clipPath></defs>`;

/** The F blade alone, at an explicit pixel size. */
const symbolSvg = (color, w, h) =>
	`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="${SYMBOL.viewBox}">${defs}${pathTags(color)}</svg>`;

/** The full "FPT Digital" lockup, at an explicit pixel size. */
const lockupSvg = (color, w, h) =>
	`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${LOCKUP.w} ${LOCKUP.h}">` +
	`<g fill="${color}" fill-rule="nonzero">${PATHS.map((d) => `<path d="${d}"/>`).join('')}</g></svg>`;

/** Vector favicon: navy field + centred white blade. */
function faviconSvg(size = 512, ratio = 0.62) {
	const gh = size * ratio;
	const gw = gh * SYMBOL.aspect;
	const s = gh / SYMBOL.h;
	const tx = (size - gw) / 2;
	const ty = (size - gh) / 2;
	return (
		`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">` +
		`<rect width="${size}" height="${size}" fill="${NAVY}"/>${defs}` +
		`<g transform="translate(${tx} ${ty}) scale(${s}) translate(${-SYMBOL.x} ${-SYMBOL.y})">${pathTags(WHITE)}</g></svg>`
	);
}

/**
 * Square navy tile with the blade centred. Full-bleed on purpose: the app clips
 * to rounded-full in CSS and iOS/Android apply their own mask shapes, so a
 * baked-in corner radius would fight all three.
 */
async function tile(size, { ratio, flatten = false } = {}) {
	const gh = Math.max(1, Math.round(size * ratio));
	const gw = Math.max(1, Math.round(gh * SYMBOL.aspect));
	const glyph = await sharp(Buffer.from(symbolSvg(WHITE, gw, gh)))
		.png()
		.toBuffer();
	let img = sharp({
		create: { width: size, height: size, channels: 4, background: NAVY }
	}).composite([{ input: glyph, gravity: 'centre' }]);
	if (flatten) img = img.flatten({ background: NAVY });
	return img.png().toBuffer();
}

/** Wide transparent lockup, for the boot splash. */
async function splash(color, w = 1030) {
	const h = Math.round(w / LOCKUP.aspect);
	return sharp(Buffer.from(lockupSvg(color, w, h)))
		.png()
		.toBuffer();
}

/** Minimal PNG-in-ICO container (supported by every browser since Vista). */
function buildIco(entries) {
	const n = entries.length;
	const header = Buffer.alloc(6);
	header.writeUInt16LE(0, 0);
	header.writeUInt16LE(1, 2);
	header.writeUInt16LE(n, 4);
	const dir = Buffer.alloc(16 * n);
	let offset = 6 + 16 * n;
	entries.forEach(({ size, buf }, i) => {
		const o = i * 16;
		dir.writeUInt8(size >= 256 ? 0 : size, o);
		dir.writeUInt8(size >= 256 ? 0 : size, o + 1);
		dir.writeUInt8(0, o + 2);
		dir.writeUInt8(0, o + 3);
		dir.writeUInt16LE(1, o + 4);
		dir.writeUInt16LE(32, o + 6);
		dir.writeUInt32LE(buf.length, o + 8);
		dir.writeUInt32LE(offset, o + 12);
		offset += buf.length;
	});
	return Buffer.concat([header, dir, ...entries.map((e) => e.buf)]);
}

async function emit(name, buf) {
	for (const tree of TREES) await writeFile(join(tree, name), buf);
	console.log(`  ${name.padEnd(30)} ${String(buf.length).padStart(7)} B  -> both trees`);
}

/** Renders a fragment at 40x and returns its ink bbox in SVG user units. */
async function inkBox(inner, label) {
	const S = 40;
	const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${LOCKUP.w * S}" height="${LOCKUP.h * S}" viewBox="0 0 ${LOCKUP.w} ${LOCKUP.h}">${inner}</svg>`;
	const { data, info } = await sharp(Buffer.from(svg))
		.ensureAlpha()
		.raw()
		.toBuffer({ resolveWithObject: true });
	let x0 = info.width,
		y0 = info.height,
		x1 = -1,
		y1 = -1,
		ink = 0;
	for (let y = 0; y < info.height; y++) {
		for (let x = 0; x < info.width; x++) {
			if (data[(y * info.width + x) * info.channels + 3] > 8) {
				ink++;
				if (x < x0) x0 = x;
				if (x > x1) x1 = x;
				if (y < y0) y0 = y;
				if (y > y1) y1 = y;
			}
		}
	}
	const f = (v) => (v / S).toFixed(2);
	const cover = ((ink / (info.width * info.height)) * 100).toFixed(1);
	console.log(
		`  ${label.padEnd(22)} x[${f(x0)}, ${f(x1 + 1)}] y[${f(y0)}, ${f(y1 + 1)}]  coverage ${cover}%`
	);
}

async function measure() {
	console.log('\nSubpath geometry (SVG user units):');
	for (let p = 0; p < PATHS.length; p++) {
		const subs = PATHS[p].split(/(?=M)/).filter(Boolean);
		for (let s = 0; s < subs.length; s++) {
			await inkBox(`<path d="${subs[s]}" fill="#000" fill-rule="nonzero"/>`, `path[${p}] sub ${s}`);
		}
	}
	console.log('\nCrop candidates:');
	const all = PATHS.map((d) => `<path d="${d}"/>`).join('');
	await inkBox(`<g fill="#000" fill-rule="nonzero">${all}</g>`, 'full lockup');
	await inkBox(
		`${defs}<g clip-path="url(#c)" fill="#000" fill-rule="nonzero">${all}</g>`,
		'F blade (clipped)'
	);
}

async function main() {
	const svg = await readFile(SRC_SVG, 'utf8');
	PATHS = [...svg.matchAll(/<path[^>]*\sd="([^"]+)"/g)].map((m) => m[1]);
	if (PATHS.length !== 2) throw new Error(`expected 2 paths in ${SRC_SVG}, found ${PATHS.length}`);

	if (process.argv.includes('--measure')) return measure();

	console.log('Generating FPT brand icons from fpt-digital-dark.svg\n');

	// Primary in-app logo (~20 call sites) + the server-side model-avatar
	// fallback at backend/open_webui/routers/models.py.
	const f512 = await tile(512, { ratio: 0.62 });
	await emit('favicon.png', f512);
	// Must exist: auth/+page.svelte and OnBoarding.svelte apply filter:invert(1)
	// if it 404s, which would turn the navy tile bright orange.
	await emit('favicon-dark.png', f512);
	await emit('favicon-96x96.png', await tile(96, { ratio: 0.62 }));
	await emit('apple-touch-icon.png', await tile(180, { ratio: 0.6, flatten: true }));

	// Maskable: glyph at 50% keeps it inside Android's central 80% safe circle.
	await emit('logo.png', await tile(500, { ratio: 0.5 }));
	await emit('web-app-manifest-192x192.png', await tile(192, { ratio: 0.5 }));
	await emit('web-app-manifest-512x512.png', await tile(512, { ratio: 0.5 }));

	await emit('favicon.svg', Buffer.from(faviconSvg()));
	await emit(
		'favicon.ico',
		buildIco([
			// Ratios climb as size drops: the blade's counter is the first thing
			// to mush out, and 16px needs every pixel it can get.
			{ size: 16, buf: await tile(16, { ratio: 0.8 }) },
			{ size: 32, buf: await tile(32, { ratio: 0.7 }) },
			{ size: 48, buf: await tile(48, { ratio: 0.62 }) }
		])
	);

	// The one place the light/dark split is real: app.html picks the file by
	// theme class over a #fff / #000 field. Wide lockup belongs here.
	await emit('splash.png', await splash(NAVY));
	await emit('splash-dark.png', await splash(WHITE));

	// URL /favicon.png — the universal image on:error fallback.
	await copyFile(join(TREES[0], 'favicon.png'), ROOT_FAVICON);
	console.log(
		`  ${'static/favicon.png'.padEnd(30)} ${String(f512.length).padStart(7)} B  -> repo root`
	);
	console.log('\nDone.');
}

main().catch((e) => {
	console.error(e);
	process.exit(1);
});
