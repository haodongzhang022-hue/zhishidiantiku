#!/usr/bin/env node
// scripts/learn.mjs — 个人学习进度系统（知识点 · 题库驱动）
//
// 目标：让"知识点题库"真正可用来练、可查个人进度。
//   - 会/不会有区分（会=mastered，不会=学习中/未学）
//   - 同知识点随机抽 2 道不同题，连续答对 2 道 = 该知识点「会了」
//   - 随机出题(quiz) 只从"还没会"的知识点里抽，方便补弱
//   - 进度以个人 JSON 持久化，形成"个人进度库"，方便学习和检查
//
// 知识点 = 题库中相对 questions/ 的目录（一级分类即整分类；有二级目录时按二级单元细分）。
//
// 用法：
//   node scripts/learn.mjs list                     列出全部知识点
//   node scripts/learn.mjs progress                 查看个人进度（会/不会/未学）
//   node scripts/learn.mjs test <知识点>            对某知识点做掌握测试（抽2道不同题，全对=会）
//   node scripts/learn.mjs quiz                     从"还没会"的知识点中随机刷题
//   node scripts/learn.mjs reset [知识点]           重置个人进度
// 可选：
//   --progress-file <path>  指定个人进度库路径（默认 ~/.zhishidiantiku/progress.json）
//   --answer A,B,y,AC       非交互按出题顺序给答案（逗号分隔；简答用 y 表示自评答对）
//   --no-color              关闭彩色
import { readdirSync, readFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline/promises';
import { randomInt } from 'node:crypto';

const root = process.cwd();

const useColor = !process.argv.includes('--no-color');
const c = {
  dim: (s) => (useColor ? `\x1b[90m${s}\x1b[0m` : s),
  red: (s) => (useColor ? `\x1b[31m${s}\x1b[0m` : s),
  green: (s) => (useColor ? `\x1b[32m${s}\x1b[0m` : s),
  yellow: (s) => (useColor ? `\x1b[33m${s}\x1b[0m` : s),
  cyan: (s) => (useColor ? `\x1b[36m${s}\x1b[0m` : s),
  bold: (s) => (useColor ? `\x1b[1m${s}\x1b[0m` : s),
};

// ---- 参数 ----
function parseArgs(argv) {
  const a = { _: [], answers: undefined, progressFile: undefined };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t === '--answer') a.answers = argv[++i].split(',').map((s) => s.trim()).filter(Boolean);
    else if (t === '--progress-file') a.progressFile = argv[++i];
    else if (t === '--no-color') { /* skip */ }
    else a._.push(t);
  }
  return a;
}
const A = parseArgs(process.argv.slice(2));
const cmd = A._[0];
const kpArg = A._[1];

// ---- 题目解析 ----
function field(text, key) {
  const m = text.match(new RegExp(`^[ \\t]*-[ \\t]*${key}[:：][ \\t]*(\\S.*?)[ \\t]*$`, 'm'));
  return m ? m[1].trim() : '';
}
function section(text, name) {
  const m = text.match(new RegExp(`##\\s*${name}\\s*\\n([\\s\\S]*?)(?=\\n##\\s|$)`, 'm'));
  return m ? m[1].trim() : '';
}
function parseFile(abs, kp) {
  const text = readFileSync(abs, 'utf8');
  const head = text.split(/\n##\s/)[0];
  const title = (text.match(/^#\s*题目[:：]\s*(.+)/m) || [])[1]?.trim() || '';
  return {
    id: field(head, '题目ID'),
    type: field(head, '题型'),
    cat: field(head, '分类'),
    difficulty: field(head, '难度'),
    kp,
    title,
    options: section(text, '选项'),
    answer: section(text, '答案'),
    explain: section(text, '解析'),
  };
}
function walk(dir, rel, kpMap, all) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const abs = join(dir, ent.name);
    if (ent.isDirectory()) walk(abs, join(rel, ent.name), kpMap, all);
    else if (ent.name.endsWith('.md') && ent.name !== 'README.md' && ent.name !== 'CATEGORIES.md') {
      const q = parseFile(abs, rel);
      if (!q.id) continue;
      if (!kpMap.has(rel)) kpMap.set(rel, []);
      kpMap.get(rel).push(q);
      all.push(q);
    }
  }
}
// bankDir 可传参（默认仓库根）；dir 用于从题目目录加载（默认 questions/）
function loadBank(bankDir) {
  const base = join(bankDir || root, 'questions');
  const kpMap = new Map();
  const all = [];
  walk(base, '', kpMap, all);
  return { kpMap, all };
}

// ---- 判分 ----
function normalizeAnswer(s) {
  if (s == null) return '';
  return [...new Set(String(s).toUpperCase().match(/[A-D]/g) || [])].sort().join('');
}
// 单选/多选/判断 => boolean；简答 => null（人工自评）
function grade(q, userAns) {
  if (!q.options) return null;
  const correct = normalizeAnswer(q.answer);
  const user = normalizeAnswer(userAns);
  if (!correct || !user) return null;
  return correct === user;
}

// ---- 进度库 ----
function progressPath() {
  if (A.progressFile) return A.progressFile;
  const dir = join(homedir(), '.zhishidiantiku');
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return join(dir, 'progress.json');
}
function loadProgress() {
  const p = progressPath();
  if (!existsSync(p)) return { version: 1, points: {} };
  try { return JSON.parse(readFileSync(p, 'utf8')); }
  catch { return { version: 1, points: {} }; }
}
function saveProgress(prog) {
  const p = progressPath();
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(prog, null, 2));
}
// 掌握判定：连续答对 >=2 道不同题 => mastered；答错清零
function applyAnswer(prog, kpId, q, ok) {
  const pt = prog.points[kpId] || (prog.points[kpId] = { correct: [], mastered: false, updatedAt: null });
  const list = pt.correct;
  if (ok === true) {
    if (!list.includes(q.id)) list.push(q.id);
    if (list.length >= 2) pt.mastered = true;
  } else if (ok === false) {
    list.length = 0;
    pt.mastered = false;
  }
  pt.updatedAt = new Date().toISOString();
  return pt;
}
const isMastered = (prog, kp) => !!(prog.points[kp]?.mastered);

// ---- 展示 ----
function statusTag(prog, kp) {
  const pt = prog.points[kp];
  const n = pt?.correct?.length || 0;
  if (pt?.mastered) return c.green('✅ 会了');
  if (n > 0) return c.yellow(`🚧 学习中（答对 ${n}/2 道不同题）`);
  return c.dim('○ 未学');
}
function printQuestion(q) {
  console.log('\n' + c.cyan(`【知识点：${q.kp || q.cat}】`));
  console.log(c.bold(`题目：${q.title || '(无标题)'}`));
  console.log(c.dim(`ID：${q.id}　题型：${q.type}　难度：${q.difficulty || '?'}`));
  if (q.options) console.log('\n' + q.options);
}

// 取答案：优先用 --answer 的第 seq 项；否则交互输入。返回 boolean|null|undefined(退出)
async function takeAnswer(rl, q, seq) {
  const fixed = A.answers && A.answers.length ? A.answers[Math.min(seq, A.answers.length - 1)] : null;
  if (q.options) {
    const input = fixed != null ? fixed : await rl.question('  你的答案（字母，如 A / AC；q 退出）：');
    if (!fixed && input.trim().toLowerCase() === 'q') return undefined;
    return grade(q, fixed != null ? fixed : input);
  }
  // 简答：展示参考答案自评
  console.log('\n' + c.yellow('【参考答案】'));
  console.log(q.answer || '(无)');
  const input = fixed != null ? fixed : await rl.question('  与你的作答比对，是否答对？（y/n；q 退出）：');
  if (!fixed && input.trim().toLowerCase() === 'q') return undefined;
  return /^(y|1|对|是)\b/i.test(fixed != null ? fixed : input) ? true : false;
}

// ---- 命令 ----
function cmdList(bank) {
  console.log(c.bold('题库知识点一览：'));
  for (const [kp, qs] of [...bank.kpMap].sort()) {
    console.log('  ' + c.cyan(kp) + c.dim(`（${qs.length} 题）`));
  }
  console.log(c.dim(`\n共 ${bank.all.length} 题，${bank.kpMap.size} 个知识点。`));
}
function cmdProgress(bank, prog) {
  console.log(c.bold('个人学习进度：'));
  if (bank.kpMap.size === 0) { console.log('  (题库为空)'); return; }
  for (const [kp, qs] of [...bank.kpMap].sort()) {
    const short = qs.length < 2 ? c.dim('　[题量不足，无法判定会了]') : '';
    console.log(`  ${c.cyan(kp)}  ${statusTag(prog, kp)}${c.dim(`（${qs.length} 题）`)}${short}`);
  }
  const passable = [...bank.kpMap].filter(([, qs]) => qs.length >= 2).map(([k]) => k);
  const mastered = passable.filter((kp) => isMastered(prog, kp)).length;
  const total = passable.length;
  const pct = total ? Math.round((mastered / total) * 100) : 0;
  console.log(c.dim(`\n可判定会了的 ${total} 个知识点中已会 ${mastered} 个（${pct}%）　·　进度库：${progressPath()}`));
}
async function cmdTest(bank, prog, kp) {
  const qs = bank.kpMap.get(kp);
  if (!qs || qs.length === 0) {
    console.log(c.red('✗ 未找到知识点：') + c.yellow(kp));
    console.log('  可用：' + [...bank.kpMap.keys()].join(' / '));
    return;
  }
  if (qs.length < 2) {
    console.log(c.yellow(`知识点 "${kp}" 目前仅 ${qs.length} 题，判定"会了"需 ≥2 道题。请先补充该知识点题目。`));
    return;
  }
  if (isMastered(prog, kp)) console.log(c.green(`  [${kp} 已判定「会了」，可先 reset 再重测]`));
  console.log(c.bold(`掌握测试 · ${kp}`) + c.dim(`（共 ${qs.length} 题，随机抽 2 道不同题，全对才算会）`));
  // 随机抽 2 道不同题
  const picks = [];
  while (picks.length < 2) {
    const q = qs[randomInt(qs.length)];
    if (!picks.includes(q)) picks.push(q);
  }
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  let hit = false;
  for (let i = 0; i < picks.length; i++) {
    const q = picks[i];
    await printQuestion(q);
    const res = await takeAnswer(rl, q, i);
    if (res === undefined) break;
    hit = true;
    if (res === null) { console.log(c.red('✗ 无法判分。')); break; }
    else if (res === true) {
      console.log(c.green('  ✓ 答对'));
      applyAnswer(prog, kp, q, true);
    } else {
      console.log(c.red('  ✗ 答错　正确答案：') + c.bold(q.answer));
      applyAnswer(prog, kp, q, false);
      break;
    }
    if (q.explain) console.log(c.dim('  ↳ ' + q.explain.split('\n')[0]));
  }
  rl.close();
  if (!hit) return;
  const pt = prog.points[kp];
  if (pt.mastered) console.log(c.green(`\n🎉 连续答对 2 道不同题，"${kp}" 判定为「会了」`));
  else console.log(c.yellow(`\n"${kp}" 尚未「会了」（当前连续答对 ${pt.correct.length}/2 道）。答错会清零，需连续答对 2 道不同题。`));
  saveProgress(prog);
}
async function cmdQuiz(bank, prog) {
  // 随机出题只从"还没会"且能判定的知识点（≥2 题）里抽，方便补弱
  const mastenable = [...bank.kpMap].filter(([, qs]) => qs.length >= 2).map(([k]) => k);
  const unmastered = mastenable.filter((kp) => !isMastered(prog, kp));
  if (unmastered.length === 0) {
    const hasShort = [...bank.kpMap].some(([k, qs]) => qs.length < 2 && !isMastered(prog, k));
    console.log(c.green('🎉 能判定的知识点都已「会了」，暂无更多待练题。'));
    if (hasShort) console.log(c.yellow('  提示：仍有少数知识点题量不足（<2 题），无法判定会了，请先补充题目。'));
    console.log(c.dim('  执行 reset 可重新开始学习。'));
    return;
  }
  const kp = unmastered[randomInt(unmastered.length)];
  const qs = bank.kpMap.get(kp);
  const correctSet = new Set(prog.points[kp]?.correct || []);
  const cand = qs.filter((q) => !correctSet.has(q.id));
  const pool = cand.length ? cand : qs;
  const q = pool[randomInt(pool.length)];
  console.log(c.bold('随机练习（来自还没会的知识点）'));
  await printQuestion(q);
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const res = await takeAnswer(rl, q, 0);
  rl.close();
  if (res === undefined) return;
  const pt = applyAnswer(prog, kp, q, res);
  if (res === true) {
    console.log(c.green('  ✓ 答对'));
    if (pt.mastered) console.log(c.green(`\n🎉 "${kp}" 连续答对 2 道不同题，已「会了」，将不再出现在随机出题中。`));
    else console.log(c.dim(`  （${kp} 已连续答对 ${pt.correct.length}/2 道不同题）`));
  } else if (res === false) {
    console.log(c.red('  ✗ 答错　正确答案：') + c.bold(q.answer) + c.dim('（该知识点清零重来）'));
    if (q.explain) console.log(c.dim('  ↳ ' + q.explain.split('\n')[0]));
  } else {
    console.log(c.yellow('  - 简答题已展示参考答案，请自行比对。'));
  }
  saveProgress(prog);
}
function cmdReset(prog, name) {
  if (name) {
    if (!prog.points[name]) { console.log(c.yellow(`未找到进度：${name}`)); return; }
    delete prog.points[name];
    console.log(c.green(`已重置知识点：${name}`));
  } else {
    prog.points = {};
    console.log(c.green('已重置全部个人进度。'));
  }
  saveProgress(prog);
}
function help() {
  console.log(c.bold('个人学习进度系统 · 用法'));
  console.log('  node scripts/learn.mjs list');
  console.log('  node scripts/learn.mjs progress');
  console.log('  node scripts/learn.mjs test <知识点>');
  console.log('  node scripts/learn.mjs quiz');
  console.log('  node scripts/learn.mjs reset [知识点]');
  console.log(c.dim('\n  知识点 = questions/ 下的目录（一级分类即整分类，二级目录按单元细分）。'));
  console.log(c.dim('  --answer A,B,y      非交互按出题顺序给答案（简答用 y 表示自评答对）'));
  console.log(c.dim('  --progress-file PATH  自定义进度库路径'));
}

function main() {
  const bank = loadBank();
  const prog = loadProgress();
  switch (cmd) {
    case 'list': return cmdList(bank);
    case 'progress': return cmdProgress(bank, prog);
    case 'test':
      return kpArg ? cmdTest(bank, prog, kpArg) : (console.log(c.red('缺少知识点名，示例：node scripts/learn.mjs test 开发基础')), help());
    case 'quiz': return cmdQuiz(bank, prog);
    case 'reset': return cmdReset(prog, kpArg);
    case 'help': case '-h': case '--help': return help();
    default:
      console.log(c.red('未知命令：') + (cmd || '(空)'));
      help();
  }
}
const isMainEntry =
  process.argv[1] &&
  fileURLToPath(import.meta.url) ===
    (process.argv[1].startsWith('file://') ? fileURLToPath(process.argv[1]) : process.argv[1]);
if (isMainEntry) main();

// 导出供其它模块/测试复用的核心函数
export {
  loadBank, grade, normalizeAnswer, applyAnswer, isMastered,
  field, section, progressPath, loadProgress, saveProgress,
  parseArgs,
};
