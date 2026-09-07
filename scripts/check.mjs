// scripts/check.mjs — 题库格式校验（CI 门禁）v2.1
// 硬校验红灯阻塞：元信息齐全/枚举合法/体系合法/体系-分类联动/分类白名单/题型选项联动/ID 唯一/范围引用存在/体系-范围联动
// 软校验黄灯提醒：缺解析、缺范围、编号命名建议
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const root = process.argv[2] || process.cwd();
const qDir = join(root, 'questions');
const cwdDocs = {
  categories: join(root, 'questions', 'CATEGORIES.md'),
  scopeRegistry: join(root, 'papers', 'README.md'),
};

const errors = [];
const warnings = [];

const TYPE_ENUM = new Set(['单选', '多选', '判断', '简答']); // 锁定 4 类
const DIFF_ENUM = new Set(['简单', '中等', '困难']);
const KNOWN_SYSTEMS = new Set(['AP', 'AL', 'IB', '国内', '其他']);
const TYPE_NEEDS_OPTIONS = new Set(['单选', '多选', '判断']); // 判/选必须带选项
const TYPE_NO_OPTIONS = new Set(['简答']); // 简答禁带选项
const KNOWN_TYPE_CODES = { 单选: 'MC', 多选: 'MN', 判断: 'TF', 简答: 'SA' };

// ---------- 解析白名单（按 section 头读取，避免表格串扰） ----------
function parseRegistry() {
  const cats = new Map();          // 分类 -> 所属体系
  const systems = new Set();       // 体系白名单代码
  const scopes = new Map();        // scope_id -> 所属体系（若登记了）
  try {
    const ctxt = readFileSync(cwdDocs.categories, 'utf8');
    const lines = ctxt.split('\n');
    let section = '';
    for (const line of lines) {
      if (/^##\s+/.test(line)) {
        section = line;
        continue;
      }
      if (line.trim().startsWith('|----') || !line.trim().startsWith('|')) continue;
      if (/〇、体系白名单/.test(section)) {
        // | 体系代码 | 体系名 | 说明 | owner | 时间 |
        const m = line.match(/^\|\s*(AP|AL|IB|国内|其他|[\u4e00-\u9fa5A-Za-z0-9]+)\s*\|/);
        if (m && !line.includes('体系代码')) systems.add(m[1].trim());
      } else if (/二、顶层分类白名单|顶层分类白名单/.test(section)) {
        // | 分类 | 所属体系 | 定位 | owner | 时间 |
        const m = line.match(/^\|\s*(开发基础|AP化学|[\u4e00-\u9fa5A-Za-z0-9]+)\s*\|\s*(AP|AL|IB|国内|其他)\s*\|/);
        if (m && !line.includes('所属体系|定位')) cats.set(m[1].trim(), m[2].trim());
      }
    }
  } catch {
    /* 未找到分类文件则留空 */
  }
  try {
    const stxt = readFileSync(cwdDocs.scopeRegistry, 'utf8');
    for (const line of stxt.split('\n')) {
      // scope 表：| scope_id | 名称 | 类型 | 年份 | 出处 | 学科 | 体系 | 题目量 | owner | 登记时间 |
      const m = line.match(/^\|\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-\d{4})\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*(AP|AL|IB|国内|其他)\s*\|/);
      if (m && !line.includes('scope_id')) scopes.set(m[1].trim(), m[2].trim());
    }
  } catch {
    /* 未找到范围登记则留空 */
  }
  return { cats, systems, scopes };
}

const { cats, systems, scopes } = parseRegistry();

// ---------- 遍历题目 ----------
function walk(dir) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) walk(p);
    else if (ent.name.endsWith('.md') && ent.name !== 'README.md' && ent.name !== 'CATEGORIES.md') check(p);
  }
}

function field(text, key) {
  const re = new RegExp(`^[ \\t]*-[ \\t]*${key}[:：][ \\t]*(\\S.*?)[ \\t]*$`, 'm');
  const m = text.match(re);
  return m ? m[1].trim() : '';
}

function parseMeta(text) {
  const head = text.split(/\n##\s/)[0];
  return {
    id: field(head, '题目ID'),
    diff: field(head, '难度'),
    cat: field(head, '分类'),
    system: field(head, '体系'),
    type: field(head, '题型'),
    scope: field(head, '范围'),
    owner: field(head, 'owner'),
    time: field(head, '录入时间'),
    frame: field(head, '难度口径'),
  };
}

function check(p) {
  const text = readFileSync(p, 'utf8');
  const rel = relative(root, p).replaceAll('\\', '/');
  const meta = parseMeta(text);

  if (!/##\s*题目/.test(text)) errors.push(rel + ': 缺少 "## 题目" 小节');
  if (!/##\s*答案/.test(text)) errors.push(rel + ': 缺少 "## 答案" 小节');

  // 元信息必填（用中文可读标签）
  const labels = { id: '题目ID', diff: '难度', cat: '分类', system: '体系', type: '题型', owner: 'owner', time: '录入时间' };
  for (const [k, v] of Object.entries({ id: meta.id, diff: meta.diff, cat: meta.cat, system: meta.system, type: meta.type, owner: meta.owner, time: meta.time })) {
    if (!v) errors.push(rel + `: 缺少必填元信息 "- ${labels[k]}"`);
  }

  // 枚举
  if (meta.diff && !DIFF_ENUM.has(meta.diff)) errors.push(rel + `: 难度 "${meta.diff}" 非法（应为 简单|中等|困难）`);
  if (meta.type && !TYPE_ENUM.has(meta.type)) errors.push(rel + `: 题型 "${meta.type}" 不在白名单（锁定 单选|多选|判断|简答）`);
  if (meta.system && !systems.has(meta.system)) errors.push(rel + `: 体系 "${meta.system}" 不在 CATEGORIES.md 体系白名单（应为 AP|AL|IB|国内|其他）`);

  // 可选字段「难度口径」：若填写，须为体系白名单内的体系（软校验）
  if (meta.frame && !KNOWN_SYSTEMS.has(meta.frame)) {
    warnings.push(rel + `: 难度口径 "${meta.frame}" 不在体系白名单（应为 AP|AL|IB|国内|其他）`);
  }

  // 分类白名单 + 体系-分类联动
  if (meta.cat && !cats.has(meta.cat)) {
    errors.push(rel + `: 分类 "${meta.cat}" 不在 CATEGORIES.md 白名单，请先登记 owner+时间+所属体系`);
  } else if (meta.cat && meta.system && cats.get(meta.cat) !== meta.system) {
    errors.push(rel + `: 分类 "${meta.cat}" 属于体系 "${cats.get(meta.cat)}"，与元信息体系 "${meta.system}" 不一致`);
  }
  // 目录与分类文件名前缀一致性（软提醒）
  const dirCat = rel.split('/')[1];
  if (dirCat && meta.cat && dirCat !== meta.cat) warnings.push(rel + `: 所在目录 "${dirCat}" 与元信息分类 "${meta.cat}" 不一致`);

  // 题型-选项联动
  const hasOptions = /##\s*选项/.test(text);
  const needOpt = TYPE_NEEDS_OPTIONS.has(meta.type);
  const noOpt = TYPE_NO_OPTIONS.has(meta.type);
  if (needOpt && !hasOptions) errors.push(rel + ': 选择题/判断题必须提供 "## 选项"');
  if (noOpt && hasOptions) errors.push(rel + ': 简答题禁止携带 "## 选项"');
  if (needOpt && hasOptions) {
    const opts = text.match(/^\s*[A-D][.、．]\s+/gm) || [];
    if (opts.length < 2) errors.push(rel + ': 选项应至少 2 项');
  }

  // 范围引用存在性 + 体系-范围联动
  if (meta.scope && scopes.size && !scopes.has(meta.scope)) errors.push(rel + `: 范围 "${meta.scope}" 未在 papers/README.md 登记`);
  if (meta.scope && scopes.has(meta.scope) && meta.system && scopes.get(meta.scope) !== meta.system) {
    errors.push(rel + `: 范围 "${meta.scope}" 属于体系 "${scopes.get(meta.scope)}"，与元信息体系 "${meta.system}" 不一致`);
  }
  if (!meta.scope) warnings.push(rel + ': 未填写 "范围"（建议指向试卷/大纲编号）');

  if (meta.time && !/^\d{4}-\d{2}-\d{2}$/.test(meta.time)) errors.push(rel + `: 录入时间 "${meta.time}" 应为 YYYY-MM-DD`);

  if (!/##\s*解析/.test(text)) warnings.push(rel + ': 无 "## 解析"（建议补充）');

  return { id: meta.id, rel, type: meta.type };
}

const collected = [];
function walkIds(dir) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) walkIds(p);
    else if (ent.name.endsWith('.md') && ent.name !== 'README.md' && ent.name !== 'CATEGORIES.md') {
      const r = check(p);
      if (r.id) collected.push(r);
    }
  }
}
walkIds(qDir);

const seen = new Map();
for (const c of collected) {
  if (seen.has(c.id)) errors.push(`题目ID "${c.id}" 重复：${seen.get(c.id)} 与 ${c.rel}`);
  else seen.set(c.id, c.rel);
}
for (const c of collected) {
  const code = KNOWN_TYPE_CODES[c.type];
  if (code && !new RegExp(`-${code}-\\d+$`).test(c.id)) {
    warnings.push(`${c.rel}: 编号 "${c.id}" 建议含题型码 -${code}-（更易检索）`);
  }
}

if (errors.length > 0) {
  console.error('[FAIL] 题库格式错误：');
  for (const e of errors) console.error('  - ' + e);
  process.exit(1);
}
console.log('[PASS] 全部题目格式合规（' + collected.length + ' 个题目文件）。');
if (warnings.length > 0) {
  console.log('[WARN] ' + warnings.length + ' 条建议：');
  for (const w of warnings.slice(0, 20)) console.log('  ~ ' + w);
}
