// scripts/check.mjs — 题库格式校验（CI 门禁）
// 规则：questions/**/*.md 必须含 "## 题目" 与 "## 答案"；
//       "## 选项" 与 "## 解析" 为推荐项（缺失仅警告，不阻塞）。
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const root = process.cwd();
const qDir = join(root, 'questions');
const errors = [];
const warnings = [];

function walk(dir) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) walk(p);
    else if (ent.name.endsWith('.md')) check(p);
  }
}

function check(p) {
  const text = readFileSync(p, 'utf8');
  const rel = relative(root, p).replaceAll('\\', '/');
  if (!/##\s*题目/.test(text)) errors.push(rel + ': 缺少 "## 题目" 小节');
  if (!/##\s*答案/.test(text)) errors.push(rel + ': 缺少 "## 答案" 小节');
  if (!/##\s*选项/.test(text)) warnings.push(rel + ': 无 "## 选项"（简答题可忽略）');
  if (!/##\s*解析/.test(text)) warnings.push(rel + ': 无 "## 解析"（建议补充）');
}

walk(qDir);
if (errors.length > 0) {
  console.error('[FAIL] 题库格式错误：');
  for (const e of errors) console.error('  - ' + e);
  process.exit(1);
}
console.log('[PASS] 全部题目格式合规（' + countMd() + ' 个题目文件）。');
if (warnings.length > 0) {
  console.log('[WARN] ' + warnings.length + ' 条建议：');
  for (const w of warnings.slice(0, 10)) console.log('  ~ ' + w);
}

function countMd() {
  let n = 0;
  const walk2 = (d) => {
    for (const ent of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, ent.name);
      if (ent.isDirectory()) walk2(p);
      else if (ent.name.endsWith('.md')) n++;
    }
  };
  walk2(qDir);
  return n;
}
