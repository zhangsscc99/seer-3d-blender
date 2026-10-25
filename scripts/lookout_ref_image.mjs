import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

export const OUTPUT_WIDTH = 1280;
export const OUTPUT_HEIGHT = 720;

const round = (value) => value == null ? null : Number(value.toFixed(6));
const finitePoint = (point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite);

export async function sha256File(filePath) {
  return createHash('sha256').update(await readFile(filePath)).digest('hex');
}

export function transformPoint(config, point) {
  const matrix = config.transform.originalTo1280;
  return [
    matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2],
    matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2],
  ];
}

export function validateConfig(config) {
  if (config.reference.originalSize[0] !== 2800 || config.reference.originalSize[1] !== 1272) {
    throw new Error('Lookout calibration must describe the fixed 2800x1272 source.');
  }
  if (config.transform.outputSize[0] !== OUTPUT_WIDTH || config.transform.outputSize[1] !== OUTPUT_HEIGHT) {
    throw new Error('Lookout calibration output must be exactly 1280x720.');
  }
  if (config.transform.autoRegistration !== false || config.transform.perImageAdjustment !== false) {
    throw new Error('Lookout calibration must disable per-image registration.');
  }
  const ids = new Set();
  const markers = new Set();
  for (const landmark of config.landmarks) {
    if (!landmark.id || ids.has(landmark.id)) throw new Error(`Duplicate or missing landmark id: ${landmark.id}`);
    if (markers.has(landmark.marker)) throw new Error(`Duplicate landmark marker: ${landmark.marker}`);
    ids.add(landmark.id);
    markers.add(landmark.marker);
    if (!finitePoint(landmark.referenceOriginal) || !finitePoint(landmark.reference1280)) {
      throw new Error(`Invalid reference coordinates for ${landmark.id}`);
    }
    if (!['fit', 'validation'].includes(landmark.group)) {
      throw new Error(`Invalid landmark group for ${landmark.id}`);
    }
    const transformed = transformPoint(config, landmark.referenceOriginal);
    const discrepancy = Math.hypot(...transformed.map((value, index) => value - landmark.reference1280[index]));
    if (discrepancy > 0.002) {
      throw new Error(`Stored transform disagrees with ${landmark.id} by ${discrepancy}px.`);
    }
  }
  if (config.landmarks.length < 30) throw new Error('At least 30 reference landmarks are required.');
}

export async function decodeRgb(input) {
  const { data, info } = await sharp(input)
    .toColourspace('srgb')
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (info.channels !== 3) throw new Error(`Expected three RGB channels, received ${info.channels}.`);
  return { data, width: info.width, height: info.height, channels: 3 };
}

export async function writeRawPng(raw, filePath) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await sharp(raw.data, {
    raw: { width: raw.width, height: raw.height, channels: 3 },
  }).png({ compressionLevel: 9 }).toFile(filePath);
}

async function rawPng(raw) {
  return sharp(raw.data, {
    raw: { width: raw.width, height: raw.height, channels: 3 },
  }).png({ compressionLevel: 9 }).toBuffer();
}

export async function renderFixedReference(config, referencePath) {
  const source = await decodeRgb(referencePath);
  const [expectedWidth, expectedHeight] = config.reference.originalSize;
  if (source.width !== expectedWidth || source.height !== expectedHeight) {
    throw new Error(`Reference dimensions ${source.width}x${source.height} do not match ${expectedWidth}x${expectedHeight}.`);
  }
  const [cropLeft, cropTop] = config.reference.validCrop;
  const scale = config.transform.scale;
  const [offsetX, offsetY] = config.transform.centerCropOffsetInScaledPixels;
  const width = config.transform.outputSize[0];
  const height = config.transform.outputSize[1];
  const output = Buffer.alloc(width * height * 3);
  const xSamples = [];
  const ySamples = [];

  const sample = (continuous, maximum) => {
    const clamped = Math.max(0, Math.min(maximum - 1, continuous - 0.5));
    const lower = Math.floor(clamped);
    return {
      lower,
      upper: Math.min(maximum - 1, lower + 1),
      fraction: clamped - lower,
    };
  };

  for (let x = 0; x < width; x += 1) {
    xSamples.push(sample(cropLeft + (x + 0.5 + offsetX) / scale, source.width));
  }
  for (let y = 0; y < height; y += 1) {
    ySamples.push(sample(cropTop + (y + 0.5 + offsetY) / scale, source.height));
  }

  for (let y = 0; y < height; y += 1) {
    const ys = ySamples[y];
    const row00 = ys.lower * source.width * 3;
    const row01 = ys.upper * source.width * 3;
    for (let x = 0; x < width; x += 1) {
      const xs = xSamples[x];
      const target = (y * width + x) * 3;
      const x0 = xs.lower * 3;
      const x1 = xs.upper * 3;
      const topWeight = (1 - xs.fraction) * (1 - ys.fraction);
      const rightWeight = xs.fraction * (1 - ys.fraction);
      const bottomWeight = (1 - xs.fraction) * ys.fraction;
      const bottomRightWeight = xs.fraction * ys.fraction;
      for (let channel = 0; channel < 3; channel += 1) {
        output[target + channel] = Math.round(
          source.data[row00 + x0 + channel] * topWeight +
          source.data[row00 + x1 + channel] * rightWeight +
          source.data[row01 + x0 + channel] * bottomWeight +
          source.data[row01 + x1 + channel] * bottomRightWeight,
        );
      }
    }
  }
  return { data: output, width, height, channels: 3 };
}

export function rectToPixels(rect, width = OUTPUT_WIDTH, height = OUTPUT_HEIGHT) {
  const left = Math.max(0, Math.min(width, Math.floor(rect[0])));
  const top = Math.max(0, Math.min(height, Math.floor(rect[1])));
  const right = Math.max(left, Math.min(width, Math.ceil(rect[2])));
  const bottom = Math.max(top, Math.min(height, Math.ceil(rect[3])));
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function paintRect(mask, rect, value, width, height) {
  const pixelRect = rectToPixels(rect, width, height);
  for (let y = pixelRect.top; y < pixelRect.bottom; y += 1) {
    mask.fill(value, y * width + pixelRect.left, y * width + pixelRect.right);
  }
}

export function buildMask(config, width = OUTPUT_WIDTH, height = OUTPUT_HEIGHT) {
  const mask = new Uint8Array(width * height);
  for (const include of config.mask.include) paintRect(mask, include.rect, 1, width, height);
  for (const exclude of config.mask.exclude) paintRect(mask, exclude.rect, 0, width, height);
  return mask;
}

export function computeRgbMetrics(first, second, mask, pixelRect = null) {
  const region = pixelRect ?? { left: 0, top: 0, right: first.width, bottom: first.height };
  const absolute = [0, 0, 0];
  const squared = [0, 0, 0];
  const thresholdCounts = Object.fromEntries([8, 16, 32, 64].map((threshold) => [threshold, 0]));
  let pixelCount = 0;
  for (let y = region.top; y < region.bottom; y += 1) {
    for (let x = region.left; x < region.right; x += 1) {
      const pixel = y * first.width + x;
      if (mask && !mask[pixel]) continue;
      const index = pixel * 3;
      let maximum = 0;
      for (let channel = 0; channel < 3; channel += 1) {
        const difference = second.data[index + channel] - first.data[index + channel];
        const magnitude = Math.abs(difference);
        absolute[channel] += magnitude;
        squared[channel] += difference * difference;
        if (magnitude > maximum) maximum = magnitude;
      }
      for (const threshold of [8, 16, 32, 64]) {
        if (maximum > threshold) thresholdCounts[threshold] += 1;
      }
      pixelCount += 1;
    }
  }
  if (pixelCount === 0) {
    return {
      pixelCount: 0,
      rgbMae: null,
      rgbRmse: null,
      meanRgbMae: null,
      meanRgbRmse: null,
      colorDifferencePixelRatio: { pixelMetric: 'maxAbsRgbChannel', comparison: 'strictly_greater_than', thresholds: null },
    };
  }
  const mae = absolute.map((sum) => sum / pixelCount);
  const rmse = squared.map((sum) => Math.sqrt(sum / pixelCount));
  return {
    pixelCount,
    rgbMae: mae.map(round),
    rgbRmse: rmse.map(round),
    meanRgbMae: round(mae.reduce((sum, value) => sum + value, 0) / 3),
    meanRgbRmse: round(rmse.reduce((sum, value) => sum + value, 0) / 3),
    colorDifferencePixelRatio: {
      pixelMetric: 'maxAbsRgbChannel',
      comparison: 'strictly_greater_than',
      thresholds: Object.fromEntries(Object.entries(thresholdCounts).map(([threshold, count]) => [threshold, round(count / pixelCount)])),
    },
  };
}

function createOverlay(reference, actual) {
  const data = Buffer.alloc(reference.data.length);
  for (let index = 0; index < data.length; index += 1) {
    data[index] = Math.round((reference.data[index] + actual.data[index]) / 2);
  }
  return { data, width: reference.width, height: reference.height, channels: 3 };
}

function createDifference(reference, actual, mask, gain) {
  const data = Buffer.alloc(reference.data.length);
  for (let pixel = 0; pixel < reference.width * reference.height; pixel += 1) {
    const index = pixel * 3;
    if (!mask[pixel]) {
      data[index] = 12;
      data[index + 1] = 16;
      data[index + 2] = 24;
      continue;
    }
    for (let channel = 0; channel < 3; channel += 1) {
      data[index + channel] = Math.min(255, Math.abs(actual.data[index + channel] - reference.data[index + channel]) * gain);
    }
  }
  return { data, width: reference.width, height: reference.height, channels: 3 };
}

export function evaluateLandmarks(config, actualLandmarks) {
  const actualById = new Map();
  const duplicateActualIds = new Set();
  for (const landmark of actualLandmarks ?? []) {
    if (!landmark || typeof landmark.id !== 'string') continue;
    if (actualById.has(landmark.id)) duplicateActualIds.add(landmark.id);
    else actualById.set(landmark.id, landmark);
  }
  const entries = config.landmarks.map((landmark) => {
    const actualRecord = actualById.get(landmark.id);
    const matched = finitePoint(actualRecord?.actual);
    const reference = landmark.reference1280 ?? transformPoint(config, landmark.referenceOriginal);
    const dx = matched ? actualRecord.actual[0] - reference[0] : null;
    const dy = matched ? actualRecord.actual[1] - reference[1] : null;
    return {
      id: landmark.id,
      marker: landmark.marker,
      component: landmark.component,
      group: landmark.group,
      confidence: landmark.confidence,
      uncertaintyPxOriginal: landmark.uncertaintyPxOriginal,
      referenceOriginal: landmark.referenceOriginal,
      reference1280: reference,
      model3D: landmark.model3D ?? null,
      status: matched ? 'matched' : 'pending',
      pendingReason: matched ? null : actualRecord ? 'invalid_actual_coordinates' : 'missing_actual_or_3d_anchor',
      actual: matched ? [...actualRecord.actual] : null,
      depth: Number.isFinite(actualRecord?.depth) ? actualRecord.depth : null,
      inCanvas: matched ? actualRecord.actual[0] >= 0 && actualRecord.actual[0] <= OUTPUT_WIDTH && actualRecord.actual[1] >= 0 && actualRecord.actual[1] <= OUTPUT_HEIGHT : null,
      dx: round(dx),
      dy: round(dy),
      error: matched ? round(Math.hypot(dx, dy)) : null,
    };
  });
  const summarize = (group) => {
    const selected = group === 'all' ? entries : entries.filter((entry) => entry.group === group);
    const matched = selected.filter((entry) => entry.status === 'matched');
    return {
      total: selected.length,
      matched: matched.length,
      pending: selected.length - matched.length,
      rms: matched.length ? round(Math.sqrt(matched.reduce((sum, entry) => sum + entry.error * entry.error, 0) / matched.length)) : null,
      max: matched.length ? round(Math.max(...matched.map((entry) => entry.error))) : null,
    };
  };
  const groups = { fit: summarize('fit'), validation: summarize('validation') };
  const matched = groups.fit.matched + groups.validation.matched;
  const pending = groups.fit.pending + groups.validation.pending;
  return {
    status: matched === 0 ? 'pending' : pending ? 'partial' : 'complete',
    pendingReason: matched === 0 ? 'No usable actual landmarks were supplied; 3D anchors may still be pending. Errors and RMS/max are null, not zero.' : null,
    coordinateSpace: '1280x720 canvas pixels; dx/dy are actual-reference without registration',
    rmsDefinition: 'sqrt(mean(dx^2 + dy^2)) over matched points only',
    groups,
    entries,
    unmatchedActual: (actualLandmarks ?? []).filter((landmark) => landmark && !config.landmarks.some((reference) => reference.id === landmark.id)),
    duplicateActualIds: [...duplicateActualIds],
  };
}

const escapeXml = (value) => String(value).replace(/[<>&'"]/g, (character) => ({
  '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;',
}[character]));

function markerSvg(width, height, entries, actualPanel) {
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    '<style>text{font-family:monospace;font-size:9px;paint-order:stroke;stroke:#000;stroke-width:2px;stroke-linejoin:round}.legend{font-size:12px;stroke-width:3px}</style>',
    `<rect x="8" y="8" width="${actualPanel ? 330 : 285}" height="22" fill="#000" opacity=".65"/>`,
    `<text class="legend" x="14" y="23" fill="#fff">${actualPanel ? 'magenta + = REF; green o = ACTUAL; REF only = pending' : 'REFERENCE; numeric markers map to report.json'}</text>`,
  ];
  for (const entry of entries) {
    const [rx, ry] = entry.reference1280;
    const labelX = Math.min(width - 24, Math.max(2, rx + 5));
    const labelY = Math.min(height - 3, Math.max(34, ry - 5));
    if (!actualPanel) {
      parts.push(`<circle cx="${rx}" cy="${ry}" r="3" fill="none" stroke="#00e5ff" stroke-width="1.2"/>`);
      parts.push(`<text x="${labelX}" y="${labelY}" fill="#00e5ff">${entry.marker}</text>`);
      continue;
    }
    if (entry.status === 'matched') {
      const [ax, ay] = entry.actual;
      parts.push(`<line x1="${rx}" y1="${ry}" x2="${ax}" y2="${ay}" stroke="#ffe66d" stroke-width="1" opacity=".85"/>`);
      parts.push(`<circle cx="${ax}" cy="${ay}" r="3.2" fill="none" stroke="#53ff88" stroke-width="1.4"/>`);
    }
    parts.push(`<path d="M ${rx - 4} ${ry} H ${rx + 4} M ${rx} ${ry - 4} V ${ry + 4}" stroke="#ff4fd8" stroke-width="1.2"/>`);
    parts.push(`<text x="${labelX}" y="${labelY}" fill="${entry.status === 'matched' ? '#fff' : '#ffb347'}">${entry.marker}</text>`);
  }
  parts.push('</svg>');
  return Buffer.from(parts.join(''));
}

async function annotatedPanel(raw, svg) {
  return sharp(raw.data, { raw: { width: raw.width, height: raw.height, channels: 3 } })
    .composite([{ input: svg, top: 0, left: 0 }])
    .png({ compressionLevel: 9 })
    .toBuffer();
}

async function createLandmarkImage(reference, actual, landmarkReport) {
  const [referencePanel, actualPanel] = await Promise.all([
    annotatedPanel(reference, markerSvg(reference.width, reference.height, landmarkReport.entries, false)),
    annotatedPanel(actual, markerSvg(actual.width, actual.height, landmarkReport.entries, true)),
  ]);
  return sharp({ create: { width: 2560, height: 720, channels: 3, background: '#000' } })
    .composite([{ input: referencePanel, left: 0, top: 0 }, { input: actualPanel, left: 1280, top: 0 }])
    .png({ compressionLevel: 9 })
    .toBuffer();
}

async function createSideBySide(referencePng, actualPng) {
  return sharp({ create: { width: 2560, height: 720, channels: 3, background: '#000' } })
    .composite([{ input: referencePng, left: 0, top: 0 }, { input: actualPng, left: 1280, top: 0 }])
    .png({ compressionLevel: 9 })
    .toBuffer();
}

async function writeRoiComparison({ roi, pixelRect, referencePng, actualPng, differencePng, outDir }) {
  const extract = { left: pixelRect.left, top: pixelRect.top, width: pixelRect.width, height: pixelRect.height };
  const [referenceCrop, actualCrop, differenceCrop] = await Promise.all([
    sharp(referencePng).extract(extract).png().toBuffer(),
    sharp(actualPng).extract(extract).png().toBuffer(),
    sharp(differencePng).extract(extract).png().toBuffer(),
  ]);
  const width = pixelRect.width * 3;
  const headerHeight = 28;
  const label = (text, center) => `<text x="${center}" y="18" text-anchor="middle" fill="#fff" font-family="monospace" font-size="11">${escapeXml(text)}</text>`;
  const header = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${headerHeight}"><rect width="100%" height="100%" fill="#101722"/>${label(`${roi.id} REF`, pixelRect.width / 2)}${label('ACTUAL', pixelRect.width * 1.5)}${label('DIFF x4 / masked', pixelRect.width * 2.5)}</svg>`);
  const filePath = path.join(outDir, 'rois', `${roi.id}.png`);
  await sharp({ create: { width, height: pixelRect.height + headerHeight, channels: 3, background: '#101722' } })
    .composite([
      { input: header, left: 0, top: 0 },
      { input: referenceCrop, left: 0, top: headerHeight },
      { input: actualCrop, left: pixelRect.width, top: headerHeight },
      { input: differenceCrop, left: pixelRect.width * 2, top: headerHeight },
    ])
    .png({ compressionLevel: 9 })
    .toFile(filePath);
  return path.relative(outDir, filePath).split(path.sep).join('/');
}

export async function generateImageReport({
  rootDir,
  config,
  configPath,
  actualPath,
  repeatPath,
  outDir,
  actualCapture,
  repeatCapture,
  thirdPerson = null,
  provenance,
  browser = null,
  server = null,
  mode = 'capture',
  selfTest = null,
}) {
  validateConfig(config);
  const referencePath = path.resolve(rootDir, config.reference.path);
  const referenceHash = await sha256File(referencePath);
  if (referenceHash !== config.reference.sha256) {
    throw new Error(`Reference SHA-256 mismatch for ${referencePath}: expected ${config.reference.sha256}, received ${referenceHash}.`);
  }
  const reference = await renderFixedReference(config, referencePath);
  const [actual, repeat] = await Promise.all([decodeRgb(actualPath), decodeRgb(repeatPath)]);
  for (const [name, image] of [['actual', actual], ['repeat', repeat]]) {
    if (image.width !== OUTPUT_WIDTH || image.height !== OUTPUT_HEIGHT) {
      throw new Error(`${name}.png must be 1280x720; received ${image.width}x${image.height}.`);
    }
  }
  await mkdir(path.join(outDir, 'rois'), { recursive: true });
  const mask = buildMask(config);
  const maskedPixelCount = mask.reduce((sum, value) => sum + value, 0);
  const globalMetrics = computeRgbMetrics(reference, actual, mask);
  const noiseMetrics = computeRgbMetrics(actual, repeat, mask);
  const landmarkReport = evaluateLandmarks(config, actualCapture?.contract?.landmarks ?? []);
  const difference = createDifference(reference, actual, mask, config.metrics.differenceImageGain);
  const overlay = createOverlay(reference, actual);
  const [referencePng, differencePng] = await Promise.all([rawPng(reference), rawPng(difference)]);
  const actualPng = await rawPng(actual);
  const sideBySidePng = await createSideBySide(referencePng, actualPng);
  const landmarksPng = await createLandmarkImage(reference, actual, landmarkReport);

  await Promise.all([
    writeRawPng(reference, path.join(outDir, 'reference_1280.png')),
    writeRawPng(overlay, path.join(outDir, 'overlay.png')),
    writeRawPng(difference, path.join(outDir, 'diff.png')),
    writeFile(path.join(outDir, 'side_by_side.png'), sideBySidePng),
    writeFile(path.join(outDir, 'landmarks.png'), landmarksPng),
  ]);

  const regions = {};
  for (const roi of config.rois) {
    const pixelRect = rectToPixels(roi.image1280, OUTPUT_WIDTH, OUTPUT_HEIGHT);
    regions[roi.id] = {
      originalRect: roi.original,
      image1280Rect: roi.image1280,
      pixelRect,
      referenceVsActual: computeRgbMetrics(reference, actual, mask, pixelRect),
      actualVsRepeatNoise: computeRgbMetrics(actual, repeat, mask, pixelRect),
      comparisonImage: await writeRoiComparison({ roi, pixelRect, referencePng, actualPng, differencePng, outDir }),
    };
  }

  const report = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    mode,
    imageReportStatus: 'complete',
    calibrationId: config.id,
    calibrationPath: path.relative(rootDir, configPath).split(path.sep).join('/'),
    reference: { ...config.reference, sha256Verified: referenceHash },
    transform: config.transform,
    cameraInitial: config.camera,
    mask: { ...config.mask, maskedPixelCount },
    policy: {
      autoRegistration: false,
      perImageAdjustment: false,
      colorMatching: false,
      syntheticSimilarityScore: false,
      differenceImageGain: config.metrics.differenceImageGain,
      differenceOutsideMaskRgb: [12, 16, 24],
      overlayReferenceWeight: 0.5,
    },
    image: {
      size: [OUTPUT_WIDTH, OUTPUT_HEIGHT],
      referenceVsActual: globalMetrics,
      actualVsRepeatNoise: noiseMetrics,
      regions,
    },
    landmarks: landmarkReport,
    captures: {
      actual: actualCapture ?? null,
      repeat: repeatCapture ?? null,
      thirdPerson: thirdPerson ?? null,
    },
    browser,
    server,
    provenance,
    selfTest,
    files: {
      reference: 'reference_1280.png',
      actual: 'actual.png',
      repeat: 'repeat.png',
      sideBySide: 'side_by_side.png',
      overlay: 'overlay.png',
      diff: 'diff.png',
      landmarks: 'landmarks.png',
      thirdPerson: thirdPerson ? 'third_person.png' : null,
      roiDirectory: 'rois',
    },
  };
  await writeFile(path.join(outDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
  return report;
}
