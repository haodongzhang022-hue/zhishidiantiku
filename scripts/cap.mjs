#!/usr/bin/env node
// scripts/cap.mjs — 跨库能力索引查询工具（Capability Registry 检索）
//
// 目标：让「跨库能力注册与索引机制」（capabilities/registry.md + gaps.md）可被程序化查询。
//   - 有能力 → 返回该能力「可用」状态 + 来源库 + 调用入口 → 按入口自动匹配调用
//   - 无能力 / 缺口 → 返回「缺口」状态 + 获取/增强引导 → 引导玩家去获取，而非"不知道有这个机制"
//
// 数据源：capabilities/registry.md（能力注册表，Markdown 表格）+ capabilities/gaps.md（缺口引导）
//
// 用法：
//   node scripts/cap.mjs available                列出所有「可用」能力
//   node scripts/cap.mjs gaps                     列出所有「缺口」能力（应有无缺）
//   node scripts/cap.mjs find <能力代码或关键字>   查询某能力：状态/来源/入口/缺口引导
//   node scripts/cap.mjs domains                  按能力域汇总统计（可用数/缺口数）
//   node scripts/cap.mjs all                      列出全部能力
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = process.cwd();
const __dirname = dirname(fileURLToPath(import.meta.url));

const useColor = !process.argv.includes('--no-color');
const c = {
  dim: (s) => (useColor ? `\x1b[90m${s}\x1b[0m` : s),
  red: (s) => (useColor ? `\x1b[31m${s}\x1b[0m` : s),
  green: (s) => (useColor ? `\x1b[32m${s}\x1b[0m` : s),
  yellow: (s) => (useColor ? `\x1b[33m${s}\x1b[0m` : s),
  cyan: (s) => (useColor ? `\x1b[36m${s}\x1b[0m` : s),
  bold: (s) => (useColor ? `\x1b[1m${s}\x1b[0m` : s),
};

function loadRegistry() {
  const file = join(root, 'capabilities', 'registry.md');
  const text = readFileSync(file, 'utf8');
  const rows = [];
  for (const line of text.split('\n')) {
    // 能力行：`| \`cap.xxx\` | ... |`
    const m = line.match(/^\|\s*`(cap\.[\w.-]+)`\s*\|(.*)\|$/);
    if (!m) continue;
    const cells = m[2].split('|').map((s) => s.trim());
    // cells 顺序：能力名|类型|来源库|调用入口|状态|owner|登记时间
    if (cells.length < 7) continue;
    rows.push({
      code: m[1],
      name: cells[0] || '',
      type: cells[1] || '',
      source: cells[2] || '',
      entry: cells[3] || '',
      status: cells[4] || '',
      owner: cells[5] || '',
      date: cells[6] || '',
    });
  }
  return rows;
}

function loadGaps() {
  const file = join(root, 'capabilities', 'gaps.md');
  if (!requireExists(file)) return [];
  const text = readFileSync(file, 'utf8');
  const rows = [];
  for (const line of text.split('\n')) {
    // 速览表行：| G1 | `cap.xxx` | 能力名 | 状态 | 说明 |
    const m = line.match(/^\|\s*(G\d+)\s*\|\s*`(cap\.[\w.-]+)`\s*\|(.*)\|$/);
    if (!m) continue;
    const cells = m[3].split('|').map((s) => s.trim());
    rows.push({ id: m[1], code: m[2], name: cells[0] || '', status: cells[1] || '', desc: cells[2] || '' });
  }
  return rows;
}

function requireExists(p) {
  try { readFileSync(p); return true; } catch { return false; }
}

function colorStatus(status) {
  if (status === '可用') return c.green(status);
  if (status === '缺口') return c.red(status);
  return c.yellow(status);
}

function showRow(r) {
  console.log(
    `${c.cyan(r.code)}  ${r.name}  [${colorStatus(r.status)}]`,
    r.status === '可用' ? `· ${c.dim(r.entry || r.source)}` : c.dim('（应有无缺 → 见 gaps）')
  );
}

function findCapabilities(rows, keyword) {
  const k = keyword.toLowerCase();
  return rows.filter(
    (r) =>
      r.code.toLowerCase().includes(k) ||
      r.name.toLowerCase().includes(k) ||
      r.type.toLowerCase().includes(k) ||
      r.source.toLowerCase().includes(k)
  );
}

function renderGap(capCode) {
  const gaps = loadGaps();
  const hit = gaps.find((g) => g.code === capCode);
  if (!hit) return '';
  // 在 gaps.md 找到对应章节（### G#）到下一个 ### 前的内容
  const file = join(root, 'capabilities', 'gaps.md');
  const lines = readFileSync(file, 'utf8').split('\n');
  const start = lines.findIndex((l) => l.trim() === `### ${hit.id}` || l.trim().startsWith(`### ${hit.id}｜`) || l.trim().startsWith(`### ${hit.id} `));
  if (start === -1) return '';
  let buf = [];
  for (let i = start + 1; i < lines.length; i++) {
    if (lines[i].trim().startsWith('### ')) break;
    buf.push(lines[i]);
  }
  return buf.join('\n').trim();
}

const args = process.argv.slice(2).filter((a) => a !== '--no-color');
const rows = loadRegistry();

function summary() {
  const usable = rows.filter((r) => r.status === '可用').length;
  const gap = rows.filter((r) => r.status === '缺口').length;
  return { usable, gap, total: rows.length };
}

switch (args[0]) {
  case 'available': {
    const usable = rows.filter((r) => r.status === '可用');
    console.log(c.bold(`可用能力（${usable.length} 项，可自动匹配调用）:`));
    usable.forEach((r) => { showRow(r); console.log(`   入口: ${c.dim(r.entry || r.source)}`); });
    break;
  }
  case 'gaps': {
    const gap = rows.filter((r) => r.status === '缺口');
    console.log(c.bold(`缺口能力（${gap.length} 项，应有无缺 → 可获取增强）:`));
    gap.forEach((r) => { showRow(r); });
    console.log(c.dim('  获取/增强引导见 capabilities/gaps.md（node scripts/cap.mjs gap <代码> 可查看单项引导）'));
    break;
  }
  case 'gap': {
    const kw = args[1];
    if (!kw) { console.log(c.yellow('用法: node scripts/cap.mjs gap <能力代码，如 cap.mishu.route>')); break; }
    const hit = rows.find((r) => r.code.toLowerCase() === kw.toLowerCase() || r.name.includes(kw));
    if (!hit) { console.log(c.yellow(`未登记能力「${kw}」。它属本业务应有无缺 → 建议登记为缺口并进 gaps 清单。`)); break; }
    if (hit.status !== '缺口') { console.log(c.green(`${hit.code} 状态=${hit.status}（非缺口）。`)); break; }
    console.log(c.bold(`${hit.code} · ${hit.name}`));
    console.log(renderGap(hit.code) || c.dim('（gaps.md 中暂无展开引导）'));
    break;
  }
  case 'find': {
    const kw = args[1];
    if (!kw) { console.log(c.yellow('用法: node scripts/cap.mjs find <能力代码或关键字>')); break; }
    const hits = findCapabilities(rows, kw);
    if (hits.length === 0) {
      const s = summary();
      console.log(c.yellow(`未找到能力「${kw}」。本仓现有 ${s.total} 项能力（可用 ${s.usable} / 缺口 ${s.gap}）。`));
      console.log(c.dim('若它是应有关键能力但未登记 → 建议登记到 capabilities/registry.md（状态=缺口）并写进 gaps.md。'));
      break;
    }
    hits.forEach((r) => {
      console.log('---');
      console.log(`${c.cyan(r.code)}  ${r.name}`);
      console.log(`  类型: ${r.type}`);
      console.log(`  状态: ${colorStatus(r.status)}`);
      console.log(`  来源: ${c.dim(r.source || '—')}`);
      console.log(`  入口: ${c.dim(r.entry || '—')}`);
      console.log(`  owner: ${c.dim(r.owner)}  ${c.dim(r.date)}`);
      if (r.status === '缺口') {
        const guide = renderGap(r.code);
        console.log(c.dim('  → 缺口引导:') + (guide ? `\n${guide.split('\n').map((l) => '    ' + l).join('\n')}` : c.dim('（见 gaps.md）')));
      }
    });
    break;
  }
  case 'domains': {
    const map = new Map();
    rows.forEach((r) => {
      // 域 = 按 registry.md 分组，这里近似用 type + 分组头；简化为按 缺口/可用 统计
      const key = r.type;
      const k2 = (map.get(key) || { usable: 0, gap: 0 });
      if (r.status === '可用') k2.usable++;
      else if (r.status === '缺口') k2.gap++;
      map.set(key, k2);
    });
    console.log(c.bold('能力分布（按类型统计）:'));
    for (const [k, v] of map) {
      console.log(`  ${c.cyan(k)}: 可用 ${c.green(v.usable)} / 缺口 ${c.red(v.gap)}`);
    }
    break;
  }
  case 'all':
  default: {
    const s = summary();
    console.log(c.bold(`全部能力（共 ${s.total} 项）:`));
    rows.forEach((r) => { showRow(r); });
    console.log('');
    console.log(`可用 ${c.green(s.usable)} / 缺口 ${c.red(s.gap)}。`);
    console.log(c.dim('子命令: available | gaps | gap <code> | find <kw> | domains | all'));
    break;
  }
}
