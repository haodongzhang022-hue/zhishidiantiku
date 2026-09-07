// scripts/__tests__/graph.test.mjs — graph.mjs（L0→L1→L2 知识图谱）自测
// 用法：node --test scripts/__tests__/graph.test.mjs
import { test } from 'node:test';
import assert from 'node:assert';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const script = resolve(repoRoot, 'scripts', 'graph.mjs');

function run(args = []) {
  return execFileSync('node', [script, ...args, '--no-color'], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
}

test('stats: 图谱包含 L0 知识点 / L2 场景 / L1 题目', () => {
  const out = run(['stats']);
  assert.match(out, /L0 知识点节点: \d+/);
  assert.match(out, /L2 使用场景节点: \d+/);
  assert.match(out, /L1 题目节点\(全库\): \d+/);
});

test('--check: seed 关系引用一致 PASS', () => {
  const out = run(['--check']);
  assert.match(out, /PASS/);
});

test('by-scene: 场景→题目返回精确刷题集', () => {
  const out = run(['by-scene', 'S.ap-chem-exam']);
  assert.match(out, /场景 S\.ap-chem-exam → 需掌握/);
  assert.match(out, /AP-CHEM-CB-2024/); // 返回题目 ID
});

test('by-kp: 知识点→覆盖题目', () => {
  const out = run(['by-kp', 'K.AP-CHEM.electron-config']);
  assert.match(out, /知识点 K\.AP-CHEM\.electron-config → 题目/);
  assert.match(out, /AP-CHEM-CB-2024/);
});

test('layers: 列出 L0 与 L2 层', () => {
  const out = run(['layers']);
  assert.match(out, /L0 · 最小知识点/);
  assert.match(out, /L2 · 使用场景/);
  assert.match(out, /K\.AP-CHEM\.kinetics/);
});

test('jump: 知识点→题目→场景 全链路', () => {
  const out = run(['jump', 'K.AP-CHEM.thermochem']);
  assert.match(out, /K\.AP-CHEM\.thermochem/);
  assert.match(out, /covered_by L1/);
  assert.match(out, /requires 该知识点的 L2 场景/);
});

test('graph-seed.json: L0 知识点引用 topic 字段完整', () => {
  const seed = JSON.parse(readFileSync(resolve(repoRoot, 'graph', 'graph-seed.json'), 'utf8'));
  assert.ok(Object.keys(seed.l0).length >= 10);
  assert.ok(Object.keys(seed.l2).length >= 1);
  // requires 关系的 from 都应在 l2、to 都应在 l0
  for (const r of seed.relations) {
    assert.ok(seed.l2[r.from], `requires 起点不在 l2: ${r.from}`);
    assert.ok(seed.l0[r.to], `requires 终点不在 l0: ${r.to}`);
  }
});
