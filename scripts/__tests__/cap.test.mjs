// scripts/__tests__/cap.test.mjs — cap.mjs（跨库能力索引工具）自测
// 用法：node --test scripts/__tests__/cap.test.mjs
import { test } from 'node:test';
import assert from 'node:assert';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const script = resolve(repoRoot, 'scripts', 'cap.mjs');

function run(args = []) {
  return execFileSync('node', [script, ...args, '--no-color'], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
}

// ---------- 基础解析 ----------
test('all: 解析 23 项能力（可用 16 / 缺口 7）', () => {
  const out = run(['all']);
  assert.match(out, /全部能力（共 23 项）/);
  assert.match(out, /可用 16 \/ 缺口 7/);
});

test('available: 列出 16 项可用能力', () => {
  const out = run(['available']);
  assert.match(out, /可用能力（16 项，可自动匹配调用）/);
});

test('gaps: 列出 7 项缺口能力', () => {
  const out = run(['gaps']);
  assert.match(out, /缺口能力（7 项，应有无缺 → 可获取增强）/);
});

test('gap: 查询缺口 cap.graph.func 不应越界吞并后续章节', () => {
  const out = run(['gap', 'cap.graph.func']);
  assert.match(out, /cap\.graph\.func · 函数\+向量层间跳转/);
  // 不应包含后续"如何驱动缺口收口"章节内容
  assert.doesNotMatch(out, /如何驱动缺口收口/);
  assert.doesNotMatch(out, /变更历史/);
});

test('gap: 查询可用能力应提示非缺口', () => {
  const out = run(['gap', 'cap.arch.total']);
  assert.match(out, /状态=可用（非缺口）/);
});

test('gap: 未登记能力应提示可登记', () => {
  const out = run(['gap', 'cap.nonexist']);
  assert.match(out, /未登记能力/);
});

test('find: 关键字搜索返回对应能力', () => {
  const out = run(['find', 'mishu']);
  assert.match(out, /cap\.mishu\.route/);
  assert.match(out, /cap\.mishu\.assign/);
  assert.match(out, /cap\.mishu\.session/);
});

test('find: 查询缺口能力时附带引导', () => {
  const out = run(['find', 'cap.graph.layer']);
  assert.match(out, /14层知识图谱/);
  assert.match(out, /缺口引导/);
});

test('find: 无匹配时给出兜底提示', () => {
  const out = run(['find', 'notfoundkeyword']);
  assert.match(out, /未找到能力/);
});

test('domains: 按类型汇总', () => {
  const out = run(['domains']);
  assert.match(out, /按类型统计/);
  assert.match(out, /跨库调用/);
  assert.match(out, /本地内置/);
});

test('gaps.md 章节号唯一性（不重复出现二/三）', () => {
  const text = readFileSync(resolve(repoRoot, 'capabilities', 'gaps.md'), 'utf8');
  const headings = text.split('\n').filter((l) => /^## /.test(l.trim()));
  const nums = headings
    .map((h) => h.match(/^## ([〇一二三四五六七八九十]+)/))
    .filter(Boolean)
    .map((m) => m[1]);
  const seen = new Set();
  for (const n of nums) {
    assert.ok(!seen.has(n), `章节号「${n}」重复`);
    seen.add(n);
  }
});
