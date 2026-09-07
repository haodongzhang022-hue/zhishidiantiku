// scripts/__tests__/learn.test.mjs — 学习进度系统核心逻辑自测
// 用法：node --test scripts/__tests__/learn.test.mjs
import { test } from 'node:test';
import assert from 'node:assert';
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { grade, normalizeAnswer, applyAnswer, isMastered, loadBank } from '../learn.mjs';

// ---------- normalize / grade ----------
test('normalizeAnswer 归一化字母并排序去重', () => {
  assert.equal(normalizeAnswer('B'), 'B');
  assert.equal(normalizeAnswer('  AC '), 'AC');
  assert.equal(normalizeAnswer('CA'), 'AC');
  assert.equal(normalizeAnswer('b'), 'B');
  assert.equal(normalizeAnswer('ABAC'), 'ABC');
  assert.equal(normalizeAnswer(null), '');
});

test('grade 单选判对错（忽略大小写与空白）', () => {
  const q = { type: '单选', answer: 'B', options: 'A..\nB..\nC..\nD..' };
  assert.equal(grade(q, 'B'), true);
  assert.equal(grade(q, 'b'), true);
  assert.equal(grade(q, 'A'), false);
  assert.equal(grade(q, 'AC'), false); // 单选多选错误
});

test('grade 多选需子集完全一致才算对', () => {
  const q = { type: '多选', answer: 'AC', options: 'A..\nB..\nC..\nD..' };
  assert.equal(grade(q, 'AC'), true);
  assert.equal(grade(q, 'CA'), true);
  assert.equal(grade(q, 'A'), false); // 漏选不算
  assert.equal(grade(q, 'ABC'), false);
});

test('grade 简答返回 null（需人工自评）', () => {
  const q = { type: '简答', answer: '要点...', options: '' };
  assert.equal(grade(q, 'x'), null);
});

// ---------- applyAnswer 掌握判定 ----------
test('连续答对 2 道不同题 => mastered', () => {
  const prog = { version: 1, points: {} };
  const q1 = { id: 'Q1' }, q2 = { id: 'Q2' };
  assert.equal(isMastered(prog, 'k1'), false);
  applyAnswer(prog, 'k1', q1, true);
  assert.equal(isMastered(prog, 'k1'), false); // 只对 1 道还没会
  applyAnswer(prog, 'k1', q2, true);           // 不同第 2 道
  assert.equal(isMastered(prog, 'k1'), true);
});

test('重复答同一道不同题不计入第 2 道（需不同的题）', () => {
  const prog = { version: 1, points: {} };
  const q = { id: 'Q1' };
  applyAnswer(prog, 'k', q, true);
  applyAnswer(prog, 'k', q, true); // 同一题答对两次
  assert.equal(isMastered(prog, 'k'), false); // 仍是 1 道不同题，未会
});

test('答错清零，回到未会', () => {
  const prog = { version: 1, points: {} };
  const q1 = { id: 'Q1' }, q2 = { id: 'Q2' };
  applyAnswer(prog, 'k', q1, true);
  applyAnswer(prog, 'k', q2, true);
  assert.equal(isMastered(prog, 'k'), true);
  applyAnswer(prog, 'k', q1, false); // 又答错一题
  assert.equal(isMastered(prog, 'k'), false);
  assert.equal(prog.points.k.correct.length, 0); // 清零重来
});

// ---------- loadBank ----------
function makeQ(dir, file, id) {
  const body = `# 题目：示例
- 题目ID：${id}
- 难度：简单
- 分类：开发基础
- 题型：单选
- owner：张三
- 录入时间：2026-09-07

## 题目
题干。

## 选项
A. a
B. b
C. c
D. d

## 答案
B

## 解析
解析。
`;
  mkdirSync(dirname(join(dir, file)), { recursive: true });
  writeFileSync(join(dir, file), body);
}
test('loadBank 按目录归知识点，并按知识点聚合题目', () => {
  const dir = mkdtempSync(join(tmpdir(), 'learn-'));
  mkdirSync(join(dir, 'questions', '开发基础'), { recursive: true });
  makeQ(join(dir, 'questions', '开发基础'), 't1.md', 'DEV-T-0001');
  makeQ(join(dir, 'questions', '开发基础'), 't2.md', 'DEV-T-0002');
  mkdirSync(join(dir, 'questions', 'AP化学', 'Unit1'), { recursive: true });
  makeQ(join(dir, 'questions', 'AP化学', 'Unit1'), 'u1.md', 'AP-CHEM-CB-2024-MC-0001');
  makeQ(join(dir, 'questions', 'AP化学', 'Unit1'), 'u2.md', 'AP-CHEM-CB-2024-MC-0002');

  const bank = loadBank(dir);
  assert.equal(bank.all.length, 4);
  assert.equal(bank.kpMap.size, 2);
  assert.ok(bank.kpMap.has('开发基础'));
  assert.ok(bank.kpMap.has('AP化学/Unit1'));
  assert.equal(bank.kpMap.get('开发基础').length, 2);
  assert.equal(bank.kpMap.get('AP化学/Unit1').length, 2);
});
