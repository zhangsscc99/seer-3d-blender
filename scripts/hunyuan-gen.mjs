import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const API = 'https://api.ai3d.cloud.tencent.com/v1/ai3d';
const ROOT = path.resolve('gen');
const RAW = path.join(ROOT, 'raw');
const JOBS = path.join(ROOT, 'jobs.json');

const env = Object.fromEntries(
  fs
    .readFileSync('.env', 'utf8')
    .split('\n')
    .filter((l) => l.includes('='))
    .map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]),
);
const KEY = env.HUNYUAN_3D_API_KEY;
if (!KEY) throw new Error('.env 中缺少 HUNYUAN_3D_API_KEY');

const STYLE = '赛尔号卡通风格，高饱和度色彩，手游场景道具，干净的造型，完整独立的单个物体';

const assets = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets.json'), 'utf8'));
const only = process.argv.slice(2);
const todo = only.length ? assets.filter((a) => only.includes(a.name)) : assets;

const jobs = fs.existsSync(JOBS) ? JSON.parse(fs.readFileSync(JOBS, 'utf8')) : {};
const save = () => fs.writeFileSync(JOBS, JSON.stringify(jobs, null, 2));

async function call(ep, body) {
  for (let i = 0; i < 5; i++) {
    try {
      const r = await fetch(`${API}/${ep}`, {
        method: 'POST',
        headers: { Authorization: KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j.Response?.Error) {
        const err = new Error(JSON.stringify(j.Response.Error));
        err.fatal = true;
        throw err;
      }
      return j.Response;
    } catch (e) {
      if (e.fatal || i === 4) throw e;
      await new Promise((r) => setTimeout(r, 3000 * (i + 1)));
    }
  }
}

async function download(url, file) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`下载失败 ${r.status}`);
  fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
}

async function run(a) {
  const dir = path.join(RAW, a.name);
  if (fs.existsSync(path.join(dir, 'model.glb')) && !process.env.FORCE) {
    console.log(`[${a.name}] 已存在，跳过`);
    return;
  }
  fs.mkdirSync(dir, { recursive: true });
  let job = jobs[a.name];
  if (!job || process.env.FORCE || job.status === 'FAIL') {
    let res;
    for (;;) {
      try {
        res = await call('submit', {
          Prompt: `${a.prompt}，${STYLE}`,
          Model: '3.1',
          EnablePBR: true,
          FaceCount: a.faces ?? 40000,
        });
        break;
      } catch (e) {
        if (!String(e.message).includes('JobNumExceed')) throw e;
        await new Promise((r) => setTimeout(r, 15000));
      }
    }
    job = jobs[a.name] = { id: res.JobId, status: 'RUN' };
    save();
    console.log(`[${a.name}] 已提交 ${res.JobId}`);
  }
  for (;;) {
    const q = await call('query', { JobId: job.id });
    if (q.Status === 'DONE') {
      const glb = q.ResultFile3Ds.find((f) => f.Type === 'GLB') ?? q.ResultFile3Ds[0];
      const zip = path.join(dir, 'result.zip');
      await download(glb.Url, zip);
      if (glb.PreviewImageUrl) await download(glb.PreviewImageUrl, path.join(dir, 'preview.png'));
      const head = fs.readFileSync(zip).subarray(0, 4).toString('latin1');
      if (head === 'glTF') fs.renameSync(zip, path.join(dir, 'model.glb'));
      else {
        execFileSync('unzip', ['-o', '-q', zip, '-d', dir]);
        const found = fs.readdirSync(dir).find((f) => f.endsWith('.glb'));
        if (!found) throw new Error(`[${a.name}] 压缩包里没有 GLB`);
        fs.renameSync(path.join(dir, found), path.join(dir, 'model.glb'));
      }
      job.status = 'DONE';
      job.credits = q.ResultCreditConsumed;
      save();
      console.log(`[${a.name}] 完成，消耗 ${q.ResultCreditConsumed} 积分`);
      return;
    }
    if (q.Status === 'FAIL') {
      job.status = 'FAIL';
      save();
      console.error(`[${a.name}] 失败: ${q.ErrorCode} ${q.ErrorMessage}`);
      return;
    }
    await new Promise((r) => setTimeout(r, 10000));
  }
}

const CONCURRENCY = Number(process.env.CONCURRENCY ?? 3);
const queue = [...todo].sort((a, b) => (jobs[b.name]?.status === 'RUN') - (jobs[a.name]?.status === 'RUN'));
await Promise.all(
  Array.from({ length: CONCURRENCY }, async () => {
    while (queue.length) {
      const a = queue.shift();
      try {
        await run(a);
      } catch (e) {
        console.error(`[${a.name}] 出错: ${e.message}`);
      }
    }
  }),
);
