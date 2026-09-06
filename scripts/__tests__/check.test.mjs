// scripts/__tests__/check.test.mjs — check.mjs 自测
// 用法：node --test scripts/__tests__/
import { test } from 'node:test';
import assert from 'node:assert';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('../check.mjs', import.meta.url));

function makeRepo({ cats = 'default', scopeReg = 'default', files = {} } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'qbank-'));
  mkdirSync(join(dir, 'questions'), { recursive: true });
  const catDefault = `# 分类白名单
| 分类 | 定位 | owner | 登记时间 | 备注 |
|------|------|-------|----------|------|
| AP化学 | x | 张三 | 2026-09-06 | |
`;
  const scopeDefault = `# 范围登记
| scope_id | 名称 |
|----------|------|
| AP-CHEM-CB-2024 | x |
`;
  writeFileSync(join(dir, 'questions', 'CATEGORIES.md'), cats === 'default' ? catDefault : cats);
  mkdirSync(join(dir, 'papers'), { recursive: true });
  writeFileSync(join(dir, 'papers', 'README.md'), scopeReg === 'default' ? scopeDefault : scopeReg);
  for (const [rel, content] of Object.entries(files)) {
    const full = join(dir, 'questions', rel);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  return dir;
}

const validQ = `# 题目：样例题
- 题目ID：AP-CHEM-CB-2024-MC-0001
- 难度：简单
- 分类：AP化学
- 题型：单选
- 范围：AP-CHEM-CB-2024
- owner：张三
- 录入时间：2026-09-06

## 题目
题干。

## 选项
A. a
B. b
C. c
D. d

## 答案
A

## 解析
解析。
`;

function run(dir) {
  return execFileSync('node', [script, dir], { encoding: 'utf8' });
}

function clean(dir) { rmSync(dir, { recursive: true, force: true }); }

test('合法题库应 PASS', () => {
  const dir = makeRepo({ files: { 'AP化学/x.md': validQ } });
  try { assert.match(run(dir), /\[PASS\]/); }
  finally { clean(dir); }
});

test('非法题型应 FAIL（题型需在白名单内）', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replace('- 题型：单选', '- 题型：填空') },
  });
  try { assert.throws(() => run(dir), /题型/); }
  finally { clean(dir); }
});

test('分类不在白名单应 FAIL', () => {
  const dir = makeRepo({
    files: { '生物学/x.md': validQ.replace('- 分类：AP化学', '- 分类：生物学') },
  });
  try { assert.throws(() => run(dir), /白名单/); }
  finally { clean(dir); }
});

test('单选缺选项应 FAIL', () => {
  const dir = makeRepo({ files: { 'AP化学/x.md': validQ.replace(/## 选项[\s\S]*?## 答案/, '## 答案') } });
  try { assert.throws(() => run(dir), /选项/); }
  finally { clean(dir); }
});

test('简答带选项应 FAIL', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replace('- 题型：单选', '- 题型：简答') },
  });
  try { assert.throws(() => run(dir), /简答题禁止/); }
  finally { clean(dir); }
});

test('题目ID重复应 FAIL', () => {
  const dir = makeRepo({
    files: {
      'AP化学/a.md': validQ,
      'AP化学/b.md': validQ.replace('# 题目：样例题', '# 题目：另一道'),
    },
  });
  try { assert.throws(() => run(dir), /重复/); }
  finally { clean(dir); }
});

test('范围引用未登记应 FAIL', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replaceAll('AP-CHEM-CB-2024', 'NOPE-2024') },
  });
  try { assert.throws(() => run(dir), /范围/); }
  finally { clean(dir); }
});

test('录入时间格式错误应 FAIL', () => {
  const dir = makeRepo({ files: { 'AP化学/x.md': validQ.replace('2026-09-06', '2026/09/06') } });
  try { assert.throws(() => run(dir), /录入时间/); }
  finally { clean(dir); }
});
