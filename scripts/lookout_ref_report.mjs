#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { access, mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  OUTPUT_HEIGHT,
  OUTPUT_WIDTH,
  decodeRgb,
  evaluateLandmarks,
  generateImageReport,
  renderFixedReference,
  sha256File,
  validateConfig,
  writeRawPng,
} from './lookout_ref_image.mjs';

const scriptPath = fileURLToPath(import.meta.url);
const imageScriptPath = fileURLToPath(new URL('./lookout_ref_image.mjs', import.meta.url));
const rootDir = path.resolve(path.dirname(scriptPath), '..');
const configPath = path.join(rootDir, 'public/models/lookout/lookout_reference.json');

function usage() {
  return `Lookout fixed-reference capture and image report

Usage:
  node scripts/lookout_ref_report.mjs [options]
  node scripts/lookout_ref_report.mjs --report-only [options]
  node scripts/lookout_ref_report.mjs --self-test [options]

Options:
  --base-url URL          Existing or auto-started Vite base URL
                          (default: LOOKOUT_BASE_URL or http://127.0.0.1:5173)
  --out-dir PATH          Output directory (default: renders/lookout/reference_report)
  --timeout-ms N          Navigation and __lookoutCapture.ready timeout (default: 60000)
  --server-timeout-ms N   Vite startup timeout (default: 30000)
  --no-start-server       Fail instead of starting a local Vite server
  --no-third-person       Skip the default third_person.png capture
  --headful               Run Chromium with a visible window
  --report-only           Reprocess outDir/actual.png and repeat.png without Chromium;
                          actual.capture.json and repeat.capture.json are used when present
  --self-test             Generate explicitly synthetic fixtures and assert image/landmark math
                          (default output: renders/lookout/reference_report_selftest)
  -h, --help              Show this help

Real capture URLs:
  ?scene=lookout&ref=1&capture=1
  ?scene=lookout&capture=1

Required page contract at window.__lookoutCapture:
  {ready:true,width:1280,height:720,
   camera:{alpha,beta,radius,target:[x,y,z],fov,fovMode},
   landmarks:[{id,actual:[x,y],depth}]}

Environment: LOOKOUT_BASE_URL and LOOKOUT_OUT_DIR are supported. No .env file is read by this tool.
`;
}

function parseOptions(argv) {
  const options = {
    baseUrl: process.env.LOOKOUT_BASE_URL || 'http://127.0.0.1:5173',
    outDir: null,
    timeoutMs: 60_000,
    serverTimeoutMs: 30_000,
    startServer: true,
    thirdPerson: true,
    headful: false,
    reportOnly: false,
    selfTest: false,
    help: false,
  };
  const value = (index, flag) => {
    if (index + 1 >= argv.length) throw new Error(`${flag} requires a value.`);
    return argv[index + 1];
  };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === '--base-url') options.baseUrl = value(index++, flag);
    else if (flag === '--out-dir') options.outDir = value(index++, flag);
    else if (flag === '--timeout-ms') options.timeoutMs = Number(value(index++, flag));
    else if (flag === '--server-timeout-ms') options.serverTimeoutMs = Number(value(index++, flag));
    else if (flag === '--no-start-server') options.startServer = false;
    else if (flag === '--no-third-person') options.thirdPerson = false;
    else if (flag === '--headful') options.headful = true;
    else if (flag === '--report-only') options.reportOnly = true;
    else if (flag === '--self-test') options.selfTest = true;
    else if (flag === '-h' || flag === '--help') options.help = true;
    else throw new Error(`Unknown option: ${flag}\n${usage()}`);
  }
  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs <= 0) throw new Error('--timeout-ms must be positive.');
  if (!Number.isFinite(options.serverTimeoutMs) || options.serverTimeoutMs <= 0) throw new Error('--server-timeout-ms must be positive.');
  if (options.reportOnly && options.selfTest) throw new Error('--report-only and --self-test are mutually exclusive.');
  const defaultOutput = options.selfTest ? 'renders/lookout/reference_report_selftest' : 'renders/lookout/reference_report';
  options.outDir = path.resolve(rootDir, options.outDir || process.env.LOOKOUT_OUT_DIR || defaultOutput);
  return options;
}

async function fileProvenance(filePath) {
  const [hash, details] = await Promise.all([sha256File(filePath), stat(filePath)]);
  return {
    path: path.relative(rootDir, filePath).split(path.sep).join('/'),
    sha256: hash,
    bytes: details.size,
  };
}

async function collectProvenance(config) {
  return {
    referenceImage: await fileProvenance(path.resolve(rootDir, config.reference.path)),
    script: await fileProvenance(scriptPath),
    imageScript: await fileProvenance(imageScriptPath),
    calibration: await fileProvenance(configPath),
    modelGlb: await fileProvenance(path.join(rootDir, 'public/models/lookout/lookout_deck.glb')),
    modelJson: await fileProvenance(path.join(rootDir, 'public/models/lookout/lookout_deck.json')),
    lookoutSource: await fileProvenance(path.join(rootDir, 'src/lookout.ts')),
  };
}

async function readJsonIfPresent(filePath) {
  try {
    return JSON.parse(await readFile(filePath, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

async function serverResponds(baseUrl) {
  try {
    const response = await fetch(baseUrl, { signal: AbortSignal.timeout(1800) });
    return response.ok;
  } catch {
    return false;
  }
}

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function ensureServer(options) {
  if (await serverResponds(options.baseUrl)) {
    return {
      report: { baseUrl: options.baseUrl, startedByScript: false },
      stop: async () => {},
    };
  }
  if (!options.startServer) {
    throw new Error(`No usable server at ${options.baseUrl}; automatic startup was disabled by --no-start-server.`);
  }
  const url = new URL(options.baseUrl);
  if (!['127.0.0.1', 'localhost', '::1'].includes(url.hostname)) {
    throw new Error(`No server at ${options.baseUrl}; automatic startup is only supported for localhost URLs.`);
  }
  const port = url.port || '5173';
  const viteBin = path.join(rootDir, 'node_modules/vite/bin/vite.js');
  await access(viteBin);
  const args = [viteBin, '--host', url.hostname, '--port', port, '--strictPort'];
  const child = spawn(process.execPath, args, {
    cwd: rootDir,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  const append = (chunk) => {
    output = `${output}${chunk}`.slice(-6000);
  };
  child.stdout.on('data', append);
  child.stderr.on('data', append);
  let exited = false;
  child.once('exit', () => { exited = true; });
  const deadline = Date.now() + options.serverTimeoutMs;
  while (Date.now() < deadline) {
    if (exited) throw new Error(`Vite exited before serving ${options.baseUrl}.\n${output}`);
    if (await serverResponds(options.baseUrl)) {
      return {
        report: {
          baseUrl: options.baseUrl,
          startedByScript: true,
          command: `node node_modules/vite/bin/vite.js --host ${url.hostname} --port ${port} --strictPort`,
        },
        stop: async () => {
          if (exited) return;
          child.kill('SIGTERM');
          await Promise.race([
            new Promise((resolve) => child.once('exit', resolve)),
            sleep(3000).then(() => { if (!exited) child.kill('SIGKILL'); }),
          ]);
        },
      };
    }
    await sleep(250);
  }
  child.kill('SIGTERM');
  throw new Error(`Vite did not serve ${options.baseUrl} within ${options.serverTimeoutMs}ms.\n${output}`);
}

function captureUrl(baseUrl, referenceMode) {
  const url = new URL(baseUrl);
  url.hash = '';
  url.searchParams.set('scene', 'lookout');
  if (referenceMode) url.searchParams.set('ref', '1');
  else url.searchParams.delete('ref');
  url.searchParams.set('capture', '1');
  return url.toString();
}

function validateContract(contract, url) {
  if (!contract || contract.ready !== true) throw new Error(`Invalid capture contract at ${url}: ready is not true.`);
  if (contract.width !== OUTPUT_WIDTH || contract.height !== OUTPUT_HEIGHT) {
    throw new Error(`Capture contract at ${url} reports ${contract.width}x${contract.height}, expected 1280x720.`);
  }
  const camera = contract.camera;
  if (!camera || !['alpha', 'beta', 'radius', 'fov'].every((key) => Number.isFinite(camera[key])) ||
      !Array.isArray(camera.target) || camera.target.length !== 3 || !camera.target.every(Number.isFinite) ||
      !['string', 'number'].includes(typeof camera.fovMode)) {
    throw new Error(`Capture contract at ${url} has an invalid camera object.`);
  }
  if (!Array.isArray(contract.landmarks)) throw new Error(`Capture contract at ${url} must contain landmarks[], even when anchors are pending.`);
}

function cameraDelta(camera, initial) {
  return {
    alpha: camera.alpha - initial.alpha,
    beta: camera.beta - initial.beta,
    radius: camera.radius - initial.radius,
    target: camera.target.map((value, index) => value - initial.target[index]),
    fov: camera.fov - initial.fov,
    actualFovMode: camera.fovMode,
    initialFovMode: initial.fovMode,
  };
}

async function inspectWebgl(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#app') || document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    if (!gl) return { available: false };
    const extension = gl.getExtension('WEBGL_debug_renderer_info');
    return {
      available: true,
      context: typeof WebGL2RenderingContext !== 'undefined' && gl instanceof WebGL2RenderingContext ? 'webgl2' : 'webgl',
      version: gl.getParameter(gl.VERSION),
      shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
      vendor: gl.getParameter(gl.VENDOR),
      renderer: gl.getParameter(gl.RENDERER),
      unmaskedVendor: extension ? gl.getParameter(extension.UNMASKED_VENDOR_WEBGL) : null,
      unmaskedRenderer: extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : null,
      maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      contextLost: gl.isContextLost(),
    };
  });
}

async function capturePage(browser, options, config, { referenceMode, filePath }) {
  const url = captureUrl(options.baseUrl, referenceMode);
  const context = await browser.newContext({
    viewport: { width: OUTPUT_WIDTH, height: OUTPUT_HEIGHT },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const consoleMessages = [];
  const pageErrors = [];
  const requestFailures = [];
  const httpErrors = [];
  page.on('console', (message) => consoleMessages.push({ type: message.type(), text: message.text(), location: message.location() }));
  page.on('pageerror', (error) => pageErrors.push({ message: error.message, stack: error.stack ?? null }));
  page.on('requestfailed', (request) => requestFailures.push({ url: request.url(), method: request.method(), failure: request.failure() }));
  page.on('response', (response) => {
    if (response.status() >= 400) httpErrors.push({ url: response.url(), status: response.status() });
  });
  await page.addInitScript(() => {
    window.__lookoutRefToolEvents = [];
    for (const type of ['webglcontextlost', 'webglcontextrestored', 'webglcontextcreationerror']) {
      document.addEventListener(type, (event) => {
        window.__lookoutRefToolEvents.push({ type, at: performance.now(), statusMessage: event.statusMessage ?? null });
      }, true);
    }
  });
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: options.timeoutMs });
    try {
      await page.waitForFunction(() => window.__lookoutCapture?.ready === true, undefined, { timeout: options.timeoutMs });
    } catch (error) {
      const diagnostic = await page.evaluate(() => ({
        title: document.title,
        captureAvailable: Boolean(window.__lookoutCapture),
        ready: window.__lookoutCapture?.ready ?? null,
        bodyText: document.body?.innerText?.slice(0, 500) ?? '',
      })).catch(() => null);
      throw new Error(
        `Timed out after ${options.timeoutMs}ms waiting for window.__lookoutCapture?.ready === true at ${url}. ` +
        `Diagnostic: ${JSON.stringify(diagnostic)}. Page errors: ${JSON.stringify(pageErrors)}. ` +
        `Recent console: ${JSON.stringify(consoleMessages.slice(-12))}`,
        { cause: error },
      );
    }
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const contract = await page.evaluate(() => JSON.parse(JSON.stringify(window.__lookoutCapture)));
    validateContract(contract, url);
    await page.screenshot({ path: filePath, type: 'png', fullPage: false, animations: 'disabled' });
    const [webgl, webglEvents, userAgent] = await Promise.all([
      inspectWebgl(page),
      page.evaluate(() => window.__lookoutRefToolEvents ?? []),
      page.evaluate(() => navigator.userAgent),
    ]);
    return {
      url,
      screenshot: path.basename(filePath),
      viewport: { width: OUTPUT_WIDTH, height: OUTPUT_HEIGHT, deviceScaleFactor: 1 },
      contract,
      cameraDeltaFromInitial: cameraDelta(contract.camera, config.camera),
      userAgent,
      webgl,
      webglEvents,
      console: consoleMessages,
      pageErrors,
      requestFailures,
      httpErrors,
    };
  } finally {
    await context.close();
  }
}

function syntheticImage(reference, variant) {
  const data = Buffer.from(reference.data);
  for (let y = 0; y < reference.height; y += 1) {
    for (let x = 0; x < reference.width; x += 1) {
      const index = (y * reference.width + x) * 3;
      for (let channel = 0; channel < 3; channel += 1) {
        const delta = ((x * 13 + y * 7 + channel * 11 + variant * 5) % 7) - 3;
        data[index + channel] = Math.max(0, Math.min(255, data[index + channel] + delta));
      }
    }
  }
  for (let y = 180; y < 230; y += 1) {
    for (let x = 80 + variant * 20; x < 230 + variant * 20; x += 1) {
      const index = (y * reference.width + x) * 3;
      data[index] = 255 - data[index];
      data[index + 1] = Math.min(255, data[index + 1] + 25);
    }
  }
  return { data, width: reference.width, height: reference.height, channels: 3 };
}

function syntheticContract(config) {
  return {
    ready: true,
    width: OUTPUT_WIDTH,
    height: OUTPUT_HEIGHT,
    camera: {
      alpha: config.camera.alpha,
      beta: config.camera.beta,
      radius: config.camera.radius,
      target: [...config.camera.target],
      fov: config.camera.fov,
      fovMode: config.camera.fovMode,
    },
    landmarks: config.landmarks.filter((landmark) => landmark.marker <= 52).map((landmark) => ({
      id: landmark.id,
      actual: landmark.group === 'fit'
        ? [landmark.reference1280[0] + 2, landmark.reference1280[1] - 3]
        : [landmark.reference1280[0] - 4, landmark.reference1280[1] + 1.5],
      depth: 40 + landmark.marker / 100,
    })),
  };
}

async function runSelfTest(options, config, provenance) {
  await mkdir(options.outDir, { recursive: true });
  const reference = await renderFixedReference(config, path.resolve(rootDir, config.reference.path));
  const actual = syntheticImage(reference, 1);
  const repeat = syntheticImage(reference, 2);
  const third = syntheticImage(reference, 3);
  await Promise.all([
    writeRawPng(actual, path.join(options.outDir, 'actual.png')),
    writeRawPng(repeat, path.join(options.outDir, 'repeat.png')),
    writeRawPng(third, path.join(options.outDir, 'third_person.png')),
  ]);
  const contract = syntheticContract(config);
  const actualCapture = { url: 'synthetic://lookout/reference', synthetic: true, contract };
  const repeatCapture = { url: 'synthetic://lookout/repeat', synthetic: true, contract };
  const thirdCapture = { url: 'synthetic://lookout/third-person', synthetic: true, contract };
  const selfTest = {
    synthetic: true,
    warning: 'actual.png, repeat.png and third_person.png are deterministic fixtures, not browser captures.',
    expectedFitDelta: [2, -3],
    expectedValidationDelta: [-4, 1.5],
    intentionallyPendingMarkers: [53, 54, 55, 56, 57],
    passed: false,
  };
  const report = await generateImageReport({
    rootDir,
    config,
    configPath,
    actualPath: path.join(options.outDir, 'actual.png'),
    repeatPath: path.join(options.outDir, 'repeat.png'),
    outDir: options.outDir,
    actualCapture,
    repeatCapture,
    thirdPerson: thirdCapture,
    provenance,
    browser: { name: 'not_launched', synthetic: true },
    server: { baseUrl: null, startedByScript: false, synthetic: true },
    mode: 'self-test',
    selfTest,
  });

  assert.equal(report.landmarks.groups.fit.total, 20);
  assert.equal(report.landmarks.groups.fit.matched, 20);
  assert.equal(report.landmarks.groups.fit.pending, 0);
  assert.ok(Math.abs(report.landmarks.groups.fit.rms - Math.sqrt(13)) < 0.00001);
  assert.ok(Math.abs(report.landmarks.groups.fit.max - Math.sqrt(13)) < 0.00001);
  assert.equal(report.landmarks.groups.validation.total, 37);
  assert.equal(report.landmarks.groups.validation.matched, 32);
  assert.equal(report.landmarks.groups.validation.pending, 5);
  assert.equal(report.landmarks.status, 'partial');
  assert.ok(report.landmarks.entries.filter((entry) => entry.status === 'pending').every((entry) => entry.error === null && entry.dx === null));
  const empty = evaluateLandmarks(config, []);
  assert.equal(empty.status, 'pending');
  assert.equal(empty.groups.fit.rms, null);
  assert.equal(empty.groups.validation.rms, null);
  assert.ok(empty.entries.every((entry) => entry.error === null));
  assert.equal(report.image.referenceVsActual.pixelCount, report.mask.maskedPixelCount);
  assert.ok(report.image.referenceVsActual.meanRgbMae > 0);
  assert.ok(report.image.actualVsRepeatNoise.meanRgbMae > 0);
  assert.equal(Object.keys(report.image.regions).length, config.rois.length);
  assert.equal(report.reference.sha256Verified, config.reference.sha256);
  assert.equal(report.policy.autoRegistration, false);
  const [sideBySide, overlay, diff, landmarks] = await Promise.all([
    decodeRgb(path.join(options.outDir, 'side_by_side.png')),
    decodeRgb(path.join(options.outDir, 'overlay.png')),
    decodeRgb(path.join(options.outDir, 'diff.png')),
    decodeRgb(path.join(options.outDir, 'landmarks.png')),
  ]);
  assert.deepEqual([sideBySide.width, sideBySide.height], [2560, 720]);
  assert.deepEqual([overlay.width, overlay.height], [1280, 720]);
  assert.deepEqual([diff.width, diff.height], [1280, 720]);
  assert.deepEqual([landmarks.width, landmarks.height], [2560, 720]);
  await Promise.all(config.rois.map((roi) => access(path.join(options.outDir, 'rois', `${roi.id}.png`))));
  const result = {
    passed: true,
    assertions: [
      'fixed source hash and 1280x720 transform',
      'reference/actual/repeat RGB and repeat-noise metrics',
      'fit RMS/max against known synthetic dx/dy',
      'partial and fully pending landmarks never produce zero errors',
      'global mask pixel counts and every component ROI',
      'side-by-side, overlay, diff and landmark output dimensions',
    ],
    fit: report.landmarks.groups.fit,
    validation: report.landmarks.groups.validation,
    fullyPendingRms: empty.groups.fit.rms,
    actualVsRepeatMeanRgbMae: report.image.actualVsRepeatNoise.meanRgbMae,
  };
  report.selfTest = { ...selfTest, passed: true, result };
  await Promise.all([
    writeFile(path.join(options.outDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`),
    writeFile(path.join(options.outDir, 'selftest-result.json'), `${JSON.stringify(result, null, 2)}\n`),
  ]);
  return report;
}

async function runReportOnly(options, config, provenance) {
  const actualCapture = await readJsonIfPresent(path.join(options.outDir, 'actual.capture.json')) ?? {
    metadataStatus: 'missing; landmarks are pending rather than zero-error',
    contract: { landmarks: [] },
  };
  const repeatCapture = await readJsonIfPresent(path.join(options.outDir, 'repeat.capture.json')) ?? {
    metadataStatus: 'missing',
    contract: { landmarks: [] },
  };
  const thirdPerson = await readJsonIfPresent(path.join(options.outDir, 'third_person.capture.json'));
  return generateImageReport({
    rootDir,
    config,
    configPath,
    actualPath: path.join(options.outDir, 'actual.png'),
    repeatPath: path.join(options.outDir, 'repeat.png'),
    outDir: options.outDir,
    actualCapture,
    repeatCapture,
    thirdPerson,
    provenance,
    browser: { name: 'not_launched', mode: 'report-only' },
    server: { baseUrl: options.baseUrl, startedByScript: false, mode: 'report-only' },
    mode: 'report-only',
  });
}

async function runCapture(options, config, provenance) {
  await mkdir(options.outDir, { recursive: true });
  let serverControl;
  let browser;
  try {
    serverControl = await ensureServer(options);
    try {
      browser = await chromium.launch({ headless: !options.headful });
    } catch (error) {
      throw new Error(`Unable to launch Playwright Chromium. Install its browser with "npx playwright install chromium". ${error.message}`, { cause: error });
    }
    const playwrightVersion = JSON.parse(await readFile(path.join(rootDir, 'node_modules/playwright/package.json'), 'utf8')).version;
    const browserInfo = {
      name: 'chromium',
      version: browser.version(),
      playwrightVersion,
      headless: !options.headful,
      viewport: [OUTPUT_WIDTH, OUTPUT_HEIGHT],
      deviceScaleFactor: 1,
    };
    const actual = await capturePage(browser, options, config, { referenceMode: true, filePath: path.join(options.outDir, 'actual.png') });
    const repeat = await capturePage(browser, options, config, { referenceMode: true, filePath: path.join(options.outDir, 'repeat.png') });
    const thirdPerson = options.thirdPerson
      ? await capturePage(browser, options, config, { referenceMode: false, filePath: path.join(options.outDir, 'third_person.png') })
      : null;
    await Promise.all([
      writeFile(path.join(options.outDir, 'actual.capture.json'), `${JSON.stringify(actual, null, 2)}\n`),
      writeFile(path.join(options.outDir, 'repeat.capture.json'), `${JSON.stringify(repeat, null, 2)}\n`),
      ...(thirdPerson ? [writeFile(path.join(options.outDir, 'third_person.capture.json'), `${JSON.stringify(thirdPerson, null, 2)}\n`)] : []),
    ]);
    return await generateImageReport({
      rootDir,
      config,
      configPath,
      actualPath: path.join(options.outDir, 'actual.png'),
      repeatPath: path.join(options.outDir, 'repeat.png'),
      outDir: options.outDir,
      actualCapture: actual,
      repeatCapture: repeat,
      thirdPerson,
      provenance,
      browser: browserInfo,
      server: serverControl.report,
      mode: 'capture',
    });
  } finally {
    if (browser) await browser.close();
    if (serverControl) await serverControl.stop();
  }
}

async function main() {
  const options = parseOptions(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }
  const config = JSON.parse(await readFile(configPath, 'utf8'));
  validateConfig(config);
  const provenance = await collectProvenance(config);
  const report = options.selfTest
    ? await runSelfTest(options, config, provenance)
    : options.reportOnly
      ? await runReportOnly(options, config, provenance)
      : await runCapture(options, config, provenance);
  console.log(JSON.stringify({
    status: 'ok',
    mode: report.mode,
    outDir: options.outDir,
    report: path.join(options.outDir, 'report.json'),
    landmarks: {
      status: report.landmarks.status,
      fit: report.landmarks.groups.fit,
      validation: report.landmarks.groups.validation,
    },
    meanRgbMae: report.image.referenceVsActual.meanRgbMae,
    actualVsRepeatMeanRgbMae: report.image.actualVsRepeatNoise.meanRgbMae,
    selfTestPassed: report.selfTest?.passed ?? null,
  }, null, 2));
}

main().catch((error) => {
  console.error(`[lookout-ref] ${error.stack ?? error.message ?? error}`);
  process.exitCode = 1;
});
