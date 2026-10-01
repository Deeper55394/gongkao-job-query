/**
 * smoke_test_frontend.mjs —— 前端逻辑冒烟测试（开发自检用，非部署必需）
 * ============================================================================
 * 做法：把 index.html 里的内联 <script> 抽出来，在极简 DOM 假环境里执行，验证两件事：
 *   阶段 1（data.json 可读取，等价于本地服务 / GitHub Pages）：默认筛选、匹配结论、
 *          身份/关键词/专业筛选、CSV 导出是否正确；
 *   阶段 2（data.json 读不到，等价于双击 file:// 打开）：能否自动退回"页面内置数据"，
 *          并给出 warn 级提示（这是"双击即用"的关键路径）。
 *
 * 运行： node tools/smoke_test_frontend.mjs
 * 退出码：0 = 全部通过，1 = 有断言失败
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const dataJson = fs.readFileSync(path.join(ROOT, 'data.json'), 'utf8');

/* ---------------- 抽出内联脚本 & 内置数据 ---------------- */
// 注意：必须排除 <script id="embedded-data" type="application/json">（那是数据不是代码）
const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
  .filter(m => !/\bsrc=/i.test(m[1]) && !/application\/json/i.test(m[1]))
  .map(m => m[2]);
if (!scripts.length) { console.error('未找到内联 <script>'); process.exit(1); }
const code = scripts.join('\n') + '\n;globalThis.__api = { state, classify, applyAndRender, majorTags, COLUMNS };';

const embeddedMatch = html.match(/<script id="embedded-data" type="application\/json">([\s\S]*?)<\/script>/i);
const embeddedRaw = embeddedMatch ? embeddedMatch[1].trim() : '';

let pass = 0, fail = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  ok ? pass++ : fail++;
  console.log(`${ok ? '[通过]' : '[失败]'} ${name}  实际=${JSON.stringify(actual)}${ok ? '' : ' 期望=' + JSON.stringify(expected)}`);
}

/* ---------------- 极简 DOM / 浏览器环境 ---------------- */
function makeEl(tag) {
  return {
    tag, innerHTML: '', textContent: '', value: '', className: '', style: {}, files: [],
    _handlers: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, f) { const on = f === undefined ? !this._s.has(c) : !!f; on ? this._s.add(c) : this._s.delete(c); return on; },
      contains(c) { return this._s.has(c); }
    },
    addEventListener(type, fn) { this._handlers[type] = fn; },
    /** 触发已注册的事件处理器（用于模拟用户点击/选文件） */
    fire(type, ev) { const h = this._handlers[type]; return h ? h(ev || { target: this, preventDefault() {} }) : undefined; },
    appendChild() {}, click() {}, remove() {}, querySelector() { return null; }
  };
}

/** 用给定的 fetch 行为，在全新假环境里跑一次前端脚本，返回其内部 API */
async function runPhase(fetchImpl, { withEmbedded = false } = {}) {
  const els = new Map();
  globalThis.document = {
    getElementById(id) {
      if (!els.has(id)) {
        const el = makeEl('#' + id);
        // 真实浏览器里，<script id="embedded-data"> 的 textContent 就是内嵌的 JSON
        if (id === 'embedded-data' && withEmbedded) el.textContent = embeddedRaw;
        els.set(id, el);
      }
      return els.get(id);
    },
    createElement(tag) { return makeEl(tag); },
    head: makeEl('head'), body: makeEl('body'),
    addEventListener() {}
  };
  globalThis.window = globalThis;
  globalThis.alert = () => {};
  globalThis.XLSX = undefined;
  globalThis.__csv = null;
  globalThis.Blob = class { constructor(parts, opts) { this.parts = parts; this.type = opts && opts.type; globalThis.__csv = parts.join(''); } };
  globalThis.URL.createObjectURL = () => 'blob:stub';
  globalThis.URL.revokeObjectURL = () => {};
  globalThis.fetch = fetchImpl;

  /* eslint-disable no-new-func */
  new Function(code)();
  await new Promise(r => setTimeout(r, 60));      // 等待 autoLoad() 完成
  return { api: globalThis.__api, els };
}

/* ============================ 阶段 1：data.json 可读取 ============================ */
console.log('—— 阶段 1：data.json 可自动读取（本地服务 / GitHub Pages）——');
const okFetch = async () => ({ ok: true, status: 200, text: async () => dataJson });
{
  const { api, els } = await runPhase(okFetch);
  const { state, classify, applyAndRender, majorTags } = api;
  const dist = () => {
    const d = { A: 0, B: 0, C: 0, D: 0 };
    state.filtered.forEach(j => { d[classify(j).level]++; });
    return d;
  };

  check('data.json 职位总数', state.jobs.length, 8);
  check('数据状态标记为示例', state.meta.data_status, 'sample');
  check('加载状态为 ok', els.get('loadState').className, 'ok');
  check('默认筛选命中条数（江苏+本科+专业标签）', state.filtered.length, 7);
  check('默认筛选结论分布', dist(), { A: 4, B: 1, C: 2, D: 0 });

  state.filters.专业 = ['生物科学'];
  applyAndRender();
  check('仅筛「生物科学」命中条数', state.filtered.length, 2);

  state.filters.专业 = ['生物科学', '生物科学类', '基础理学类', '教育类', '不限专业'];
  state.filters.身份 = ['应届'];
  applyAndRender();
  // 身份"不限"的岗位对任何身份筛选都应放行 = 3 条应届 + 3 条身份不限
  check('身份=应届 命中条数（含身份不限岗位）', state.filtered.length, 6);

  state.filters.身份 = [];
  state.filters.关键词 = ['教师资格'];
  applyAndRender();
  check('关键词「教师资格」命中条数', state.filtered.length, 1);

  state.filters.关键词 = [];
  state.filters.其他 = ['要求师范类'];
  applyAndRender();
  check('要求师范类 命中条数', state.filtered.length, 0);

  state.filters.其他 = [];
  applyAndRender();
  check('需电话咨询条数', state.filtered.filter(j => classify(j).needCall).length, 3);

  check('标签推断：生物科学（师范）', majorTags({ 专业要求原文: '生物科学（师范）、生物科学类' }), ['生物科学', '生物科学类']);
  check('标签推断：不限专业', majorTags({ 专业要求原文: '不限专业' }), ['不限专业']);
  check('标签推断：相近专业', majorTags({ 专业要求原文: '生物技术、生物工程' }), ['相近专业']);

  document.getElementById('btnCsv').onclick();
  const csv = globalThis.__csv || '';
  const csvLines = csv.replace(/^\uFEFF/, '').split('\r\n').filter(Boolean);
  check('CSV 带 UTF-8 BOM', csv.charCodeAt(0), 0xFEFF);
  check('CSV 行数 = 命中数 + 表头', csvLines.length, state.filtered.length + 1);
  check('CSV 表头包含 专业要求原文/来源链接/匹配结论',
    ['专业要求原文', '来源链接', '匹配结论'].every(h => csvLines[0].includes(h)), true);
}

/* ============================ 阶段 2：data.json 读不到（双击打开） ============================ */
console.log('\n—— 阶段 2：读不到 data.json，自动退回页面内置数据（双击 file:// 场景）——');
{
  // 模拟 file:// 下 fetch 抛异常
  const failFetch = async () => { throw new TypeError('Failed to fetch'); };
  const { api, els } = await runPhase(failFetch, { withEmbedded: true });
  const { state, classify } = api;

  check('内置数据可解析且记录数一致', state.jobs.length, JSON.parse(dataJson).jobs.length);
  check('内置数据来源标注', state.meta.data_status, 'sample');
  check('加载状态降级为 warn（而非报错）', els.get('loadState').className, 'warn');
  check('提示文案提到「内置数据」', /内置数据/.test(els.get('loadState').innerHTML), true);
  const d = { A: 0, B: 0, C: 0, D: 0 };
  state.filtered.forEach(j => { d[classify(j).level]++; });
  check('内置数据默认筛选分布一致', d, { A: 4, B: 1, C: 2, D: 0 });
}

/* ============ 阶段 3：浏览器内直接上传官方 Excel（完全不需要 Python） ============ */
console.log('\n—— 阶段 3：页面内上传官方职位表 Excel（无 Python / 无网络场景）——');
{
  const xlsxPath = path.join(ROOT, 'xlsx.full.min.js');
  const samplePath = path.join(ROOT, 'samples', '示例_江苏省考职位表.xlsx');
  if (!fs.existsSync(xlsxPath)) {
    console.log('[跳过] 未找到 xlsx.full.min.js（本地 SheetJS）');
  } else if (!fs.existsSync(samplePath)) {
    console.log('[跳过] 未找到示例职位表');
  } else {
    const XLSX = require(xlsxPath);            // 与浏览器里 <script src="xlsx.full.min.js"> 是同一个库
    const { api, els } = await runPhase(okFetch);
    const { state, classify } = api;

    check('本地 SheetJS 可加载', typeof XLSX.read === 'function', true);
    globalThis.XLSX = XLSX;                    // 模拟"同目录 xlsx.full.min.js 已就绪"，此时不需要联网

    // 造一个假的 File 对象，内容就是示例职位表
    const buf = fs.readFileSync(samplePath);
    els.get('fileExcel').files = [{
      name: '示例_江苏省考职位表.xlsx',
      arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)
    }];
    await els.get('fileExcel').fire('change');
    await new Promise(r => setTimeout(r, 80));

    check('上传后解析出的职位数', state.jobs.length, 5);
    check('数据被标记为本地导入', state.meta.data_status, 'local-import');
    check('表头映射：单位名称 -> 招录机关',
      state.jobs.some(j => String(j['招录机关']).includes('南京市教育局')), true);
    check('专业原文逐字保留',
      state.jobs.some(j => j['专业要求原文'] === '生物科学（师范）、生物科学、生物科学类'), true);
    const d = { A: 0, B: 0, C: 0, D: 0 };
    state.filtered.forEach(j => { d[classify(j).level]++; });
    check('上传后默认筛选命中', state.filtered.length, 4);
    check('上传后结论分布', d, { A: 2, B: 1, C: 1, D: 0 });
  }
}

console.log(`\n冒烟测试：通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
