#!/usr/bin/env node
// scripts/graph.mjs — L0知识点→L1题目→L2场景 知识图谱工具（函数硬通道 relations）
//
// 目标：把"解耦题库"从扁平题目表，升级为带目的链、可函数跳转的知识节点（Issue #1）。
// 层：
//   L0 最小知识点（来自 graph/graph-seed.json 的 l0 注册表）
//   L1 题目（自动从 questions/*.md 的 '- 知识点：' 字段发现）
//   L2 使用场景（来自 graph/graph-seed.json 的 l2 注册表）
// 关系（函数硬通道，双向可回溯）：
//   covered_by : L0 知识点 --被覆盖--> L1 题目   （由题目 '知识点' 字段自动建立）
//   requires   : L2 场景 --需要--> L0 知识点      （graph-seed.json 手工登记）
//
// 精准刷题链路：输入现实需求 → 命中 L2 场景 → requires 跳到 L0 知识点 →
//               covered_by 跳到 L1 题目 → 只刷与目的相关的题。
//
// 用法：
//   node scripts/graph.mjs layers                   列出各层节点
//   node scripts/graph.mjs node <id>                查单个节点详情 + 邻居
//   node scripts/graph.mjs by-kp <知识点id>         知识点→题目
//   node scripts/graph.mjs by-scene <场景id>        场景→题目（精准刷题）
//   node scripts/graph.mjs scene-from-kp <关键字>   输入现实需求/关键字→命中场景→出题
//   node scripts/graph.mjs jump <知识点id>          知识点→题目→场景 全链路
//   node scripts/graph.mjs stats                    图谱规模统计
//   node scripts/graph.mjs --check                  自检 seed 引用完整性（门禁）
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const seedPath = join(root, 'graph', 'graph-seed.json');
const qDir = join(root, 'questions');

const useColor = !process.argv.includes('--no-color');
const c = {
  bold: (s) => (useColor ? `\x1b[1m${s}\x1b[0m` : s),
  green: (s) => (useColor ? `\x1b[32m${s}\x1b[0m` : s),
  yellow: (s) => (useColor ? `\x1b[33m${s}\x1b[0m` : s),
  cyan: (s) => (useColor ? `\x1b[36m${s}\x1b[0m` : s),
  dim: (s) => (useColor ? `\x1b[90m${s}\x1b[0m` : s),
  red: (s) => (useColor ? `\x1b[31m${s}\x1b[0m` : s),
};

// ---------- 读取种子 ----------
function loadSeed() {
  const raw = readFileSync(seedPath, 'utf8');
  return JSON.parse(raw);
}

// ---------- 扫描题目，发现 L1 节点 + covered_by ----------
function walk(dir, out = []) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (ent.name.endsWith('.md') && ent.name !== 'README.md' && ent.name !== 'CATEGORIES.md') out.push(p);
  }
  return out;
}

function field(text, key) {
  const re = new RegExp(`^[ \\t]*-[ \\t]*${key}[:：][ \\t]*(\\S.*?)[ \\t]*$`, 'm');
  const m = text.match(re);
  return m ? m[1].trim() : '';
}

// 从题目文件取 题目ID + 知识点；知识点可能是"id|名称"或直接名称，这里统一规整为 seed 里的 id
function scanQuestions(seed) {
  // 建立 知识点id 别名映射：把 l0 的 name 和 topic 也作为可匹配别名
  const kpIndex = new Map(); // name/topic/子串 -> l0 id
  for (const [id, n] of Object.entries(seed.l0 || {})) {
    kpIndex.set(n.name, id);
    if (n.topic) kpIndex.set(n.topic, id);
  }
  const questions = [];   // {id, file, kpId[]}
  const coveredBy = [];   // L0 id -> [L1 question id]
  const kpById = {};
  for (const p of walk(qDir)) {
    const text = readFileSync(p, 'utf8');
    const qid = field(text, '题目ID');
    if (!qid) continue;
    const kp = field(text, '知识点') || field(text, '标签') || '';
    if (!kp) continue;
    // 知识点字段可能是 seed id、seed name 或逗号分隔多个，逐个解析
    const rawItems = kp.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    const qKp = [];
    for (const item of rawItems) {
      const id = kpIndex.get(item) || (seed.l0 && seed.l0[item] ? item : null)
        || findByIdOrName(item, seed);
      if (id) { qKp.push(id); if (!qKp.includes(id)) ; }
    }
    const uniq = [...new Set(qKp)];
    questions.push({ id: qid, file: p, kpIds: uniq });
    for (const kid of uniq) {
      (coveredBy[kid] = coveredBy[kid] || []).push(qid);
    }
  }
  return { questions, coveredBy };
}

function findByIdOrName(item, seed) {
  if (!seed.l0) return null;
  if (seed.l0[item]) return item;
  // 允许按 name 精确或包含匹配
  for (const [id, n] of Object.entries(seed.l0)) {
    if (n.name && (n.name === item || n.name.includes(item) || item.includes(n.name))) return id;
  }
  return null;
}

// ---------- 场景→题目（精准刷题核心） ----------
function sceneToQuestions(sceneId, coveredBy, seed) {
  // 场景 requires 的 L0 知识点集合
  const reqKps = (seed.relations || [])
    .filter((r) => r.from === sceneId && r.type === 'requires')
    .map((r) => r.to);
  const kpToQuestions = new Map();
  const seenQ = new Set();
  for (const kid of reqKps) {
    const qs = coveredBy[kid] || [];
    kpToQuestions.set(kid, qs);
    qs.forEach((q) => seenQ.add(q));
  }
  return { scene: sceneId, reqKps, kpToQuestions, questionIds: [...seenQ] };
}

// ---------- 输出辅助 ----------
function printLayers(seed, scan) {
  console.log(c.bold('L0 · 最小知识点') + c.dim(` (${Object.keys(seed.l0).length})`));
  for (const [id, n] of Object.entries(seed.l0)) {
    const cnt = (scan.coveredBy[id] || []).length;
    console.log(`  ${c.cyan(id)}  ${n.name}${n.topic ? c.dim('  [' + n.topic + ']') : ''} ${cnt ? c.green(`→${cnt}题`) : c.dim('→0题')}`);
  }
  console.log(c.bold('L2 · 使用场景') + c.dim(` (${Object.keys(seed.l2).length})`));
  for (const [id, n] of Object.entries(seed.l2)) {
    const { questionIds } = sceneToQuestions(id, scan.coveredBy, seed);
    console.log(`  ${c.cyan(id)}  ${n.name} ${questionIds.length ? c.green(`→${questionIds.length}题`) : c.dim('→0题')}`);
  }
}

function printNode(id, seed, scan) {
  if (seed.l0[id]) {
    console.log(c.bold('L0 知识点:') + ` ${c.cyan(id)} · ${seed.l0[id].name}`);
    const qs = scan.coveredBy[id] || [];
    console.log(c.dim('  ↓ covered_by L1 题目:'));
    if (qs.length) qs.forEach((q) => console.log(`    · ${q}`));
    else console.log(c.yellow('    暂无已标注知识点为 "' + id + '" 的题目（请先在题目文件补 `- 知识点:`）'));
  } else if (seed.l2[id]) {
    console.log(c.bold('L2 场景:') + ` ${c.cyan(id)} · ${seed.l2[id].name}`);
    const { reqKps, questionIds, kpToQuestions } = sceneToQuestions(id, scan.coveredBy, seed);
    console.log(c.dim('  ↓ requires L0 知识点:'));
    reqKps.forEach((k) => {
      const qs = kpToQuestions.get(k) || [];
      console.log(`    · ${k} ${qs.length ? c.green(`(${qs.length}题)`) : c.dim('(0题)')}`);
    });
    console.log(c.dim('  ↳ 该场景可刷题目:'));
    questionIds.forEach((q) => console.log(`    · ${q}`));
  } else {
    console.log(c.red('未找到该节点: ') + id);
  }
}

// ---------- main ----------
const args = process.argv.slice(2);
if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
  console.log(`
用法:
  node scripts/graph.mjs layers                   列出各层节点 + 关联题量
  node scripts/graph.mjs node <id>                查单节点详情（L0 见题 / L2 见题）
  node scripts/graph.mjs by-kp <知识点id>         知识点 → 覆盖它的题目
  node scripts/graph.mjs by-scene <场景id>        场景 → 需掌握知识点 → 可刷题目
  node scripts/graph.mjs scene-from-kp <关键字>   输入现实需求关键字 → 命中场景 → 出题
  node scripts/graph.mjs jump <知识点id>          知识点 → 题目 → 适用场景 全链路
  node scripts/graph.mjs stats                    图谱规模统计
  node scripts/graph.mjs --check                  自检 seed 引用完整性
`);
  process.exit(0);
}

const seed = loadSeed();
const scan = scanQuestions(seed);
const cmd = args[0];

try {
  if (cmd === '--check' || cmd === 'check') {
    const errs = [];
    // 校验 L0/L2 节点存在
    for (const r of seed.relations || []) {
      if (r.type === 'requires' && !seed.l2[r.from]) errs.push(`关系起点非 L2 场景: ${r.from}`);
      if (r.type === 'requires' && !seed.l0[r.to]) errs.push(`关系终点非 L0 知识点: ${r.to}`);
    }
    // 校验题目引用的题目 ID 确实存在（covered_by 由题目文件自动生成，天然存在）
    console.log(c.bold('图谱自检:'));
    console.log(`  L0 知识点: ${Object.keys(seed.l0).length}`);
    console.log(`  L2 场景: ${Object.keys(seed.l2).length}`);
    console.log(`  relations(seed): ${seed.relations.length}`);
    console.log(`  L1 题目(含知识点标注): ${scan.questions.length}`);
    if (errs.length) { errs.forEach((e) => console.log('  ' + c.red('[红灯] ') + e)); process.exit(1); }
    console.log(c.green('  PASS — seed 关系引用一致'));
  } else if (cmd === 'layers') {
    printLayers(seed, scan);
  } else if (cmd === 'node') {
    printNode(args[1], seed, scan);
  } else if (cmd === 'by-kp') {
    if (!args[1]) { console.log('用法: by-kp <知识点id>'); process.exit(1); }
    const qs = scan.coveredBy[args[1]] || [];
    console.log(c.bold(`知识点 ${args[1]} → 题目 (${qs.length})`));
    qs.forEach((q) => console.log('  · ' + q));
    if (!qs.length) console.log(c.yellow('  暂无标注。请把题目 `- 知识点:` 填为 seed 内某 L0 id（如 K.AP-CHEM.xxx）。'));
  } else if (cmd === 'by-scene') {
    if (!args[1]) { console.log('用法: by-scene <场景id>'); process.exit(1); }
    const { reqKps, questionIds } = sceneToQuestions(args[1], scan.coveredBy, seed);
    console.log(c.bold(`场景 ${args[1]} → 需掌握 ${reqKps.length} 个知识点 → 可刷 ${questionIds.length} 题`));
    reqKps.forEach((k) => console.log('  · ' + c.cyan(k)));
    console.log(c.dim('  ↳ 题目:'));
    questionIds.forEach((q) => console.log('    · ' + q));
  } else if (cmd === 'scene-from-kp') {
    // 精准刷题：输入现实需求关键字，命中场景
    const kw = args[1];
    if (!kw) { console.log('用法: scene-from-kp <关键字>'); process.exit(1); }
    console.log(c.bold(`输入现实需求「${kw}」→ 场景命中:`) + '\n');
    const hits = [];
    for (const [sid, s] of Object.entries(seed.l2)) {
      const text = (s.name + s.desc).toLowerCase();
      if (text.includes(kw.toLowerCase()) || kw.toLowerCase().includes(sid.toLowerCase().split('.').pop())) {
        hits.push(sid);
      }
    }
    // 也允许直接命中某 L0 知识点名（关键字即知识点）
    const kpHit = Object.entries(seed.l0).find(([, n]) =>
      (n.name && n.name.includes(kw)) || (n.topic && n.topic === kw));
    if (hits.length === 0 && kpHit) {
      // 由知识点反向找它属于哪个场景（该知识点被哪些场景 requires）
      const [kid] = kpHit;
      const parentScenes = (seed.relations || [])
        .filter((r) => r.to === kid && r.type === 'requires').map((r) => r.from);
      parentScenes.forEach((s) => hits.push(s));
    }
    if (hits.length === 0) { console.log(c.yellow('未命中场景。试试：ap-chem-exam / preq-college / chem-contest，或直接给知识点关键字。')); process.exit(0); }
    for (const sid of hits) {
      const { questionIds } = sceneToQuestions(sid, scan.coveredBy, seed);
      console.log(`  ${c.green(sid)} · ${seed.l2[sid].name}`);
      if (questionIds.length) {
        console.log(c.dim('    精准刷题建议（去重后前 N 道）:'));
        questionIds.slice(0, 15).forEach((q) => console.log('      · ' + q));
      } else console.log(c.yellow('    该场景覆盖的知识点暂无可刷题目（题库待补知识点标注）'));
      console.log('');
    }
  } else if (cmd === 'jump') {
    if (!args[1]) { console.log('用法: jump <知识点id>'); process.exit(1); }
    // 知识点 → 题目 → 场景
    const kid = args[1];
    if (!seed.l0[kid]) { console.log(c.red('未找到知识点: ') + kid); process.exit(1); }
    console.log(`${c.bold('L0')} ${c.cyan(kid)} · ${seed.l0[kid].name}`);
    const qs = scan.coveredBy[kid] || [];
    console.log(`${c.bold('↓ covered_by L1')} (${qs.length} 题)`);
    qs.forEach((q) => console.log(`   · ${q}`));
    // 反向找该知识点被哪些场景需要
    const parentScenes = (seed.relations || [])
      .filter((r) => r.to === kid && r.type === 'requires').map((r) => r.from);
    if (parentScenes.length) {
      console.log(`${c.bold('↑ requires 该知识点的 L2 场景:')}`);
      parentScenes.forEach((s) => console.log(`   · ${s} ${seed.l2[s] ? seed.l2[s].name : ''}`));
    }
  } else if (cmd === 'stats') {
    const withKp = scan.questions.length;
    const totalQ = walk(qDir).length;
    const scenes = Object.keys(seed.l2).length;
    const kps = Object.keys(seed.l0).length;
    const taggedKps = Object.keys(scan.coveredBy).filter((k) => (scan.coveredBy[k] || []).length).length;
    console.log('图谱规模:');
    console.log(`  L0 知识点节点: ${kps}`);
    console.log(`  L1 题目节点(全库): ${totalQ}  其中已挂知识点: ${withKp}`);
    console.log(`  L2 使用场景节点: ${scenes}`);
    console.log(`  关系(requires seed): ${seed.relations.length}`);
    console.log(`  已激活知识点(L0→题 非空): ${taggedKps}/${kps}`);
  } else {
    console.log(c.red('未知命令: ') + cmd + '\n运行 node scripts/graph.mjs --help 查看用法');
  }
} catch (e) {
  console.error(c.red('执行出错: ') + e.message);
  process.exit(1);
}
