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
  const catDefault = `# 分类 / 体系 / 题型白名单登记

## 〇、体系白名单
| 体系代码 | 体系名 | 说明 | owner | 登记时间 |
|----------|--------|------|-------|----------|
| AP | 美国大学先修课程 | x | 张三 | 2026-09-07 |
| 其他 | 通用/其他体系 | x | 张三 | 2026-09-07 |

## 二、顶层分类白名单
| 分类 | 所属体系 | 定位 | owner | 登记时间 | 备注 |
|------|----------|------|-------|----------|------|
| AP化学 | AP | x | 张三 | 2026-09-06 | |
| 开发基础 | 其他 | x | 张三 | 2026-09-06 | |
`;
  const scopeDefault = `# 范围登记
| scope_id | 名称 | 类型 | 年份 | 出处 | 学科 | 体系 | 题目量 | owner | 登记时间 |
|----------|------|------|------|------|------|------|--------|-------|----------|
| AP-CHEM-CB-2024 | x | exam | 2024 | src | AP化学 | AP | 1 | 张三 | 2026-09-06 |
| AL-CHEM-CIE-2024 | y | syllabus | 2024 | src | 化学 | AL | 0 | 张三 | 2026-09-07 |
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
- 体系：AP
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

test('缺少体系字段应 FAIL', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replace('- 体系：AP\n', '') },
  });
  try { assert.throws(() => run(dir), /体系/); }
  finally { clean(dir); }
});

test('体系不在白名单应 FAIL', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replace('- 体系：AP', '- 体系：XX') },
  });
  try { assert.throws(() => run(dir), /体系/); }
  finally { clean(dir); }
});

test('体系与分类所属体系不一致应 FAIL', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replace('- 体系：AP', '- 体系：其他') },
  });
  try { assert.throws(() => run(dir), /不一致/); }
  finally { clean(dir); }
});

test('体系与范围所属体系不一致应 FAIL', () => {
  // 题目体系为 AP，但引用了一个 AL 的范围 -> 体系-范围不一致
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replaceAll('AP-CHEM-CB-2024', 'AL-CHEM-CIE-2024') },
  });
  try { assert.throws(() => run(dir), /不一致/); }
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

test('难度口径合法(在体系内)应 PASS', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ + '\n' }, // 不填难度口径，或填 AP
  });
  try { assert.match(run(dir), /\[PASS\]/); }
  finally { clean(dir); }
});

test('难度口径非法应给 WARN 建议(不阻塞)', () => {
  const dir = makeRepo({
    files: { 'AP化学/x.md': validQ.replace('- 体系：AP\n', '- 体系：AP\n- 难度口径：XX\n') },
  });
  try {
    const out = run(dir); // warning 不阻塞，应正常返回
    assert.match(out, /\[PASS\]/);
    assert.match(out, /难度口径 "XX" 不在体系白名单/);
  } finally { clean(dir); }
});
