# -*- coding: utf-8 -*-
"""分数体系识别器。

输入一段学生成绩描述（自然语言/简写），通过关键词 + 数值模式 + 启发式规则
判断属于哪套体系，并提取关键分数特征。示例输入：

    "AP: Calc BC 5, Chem 4, Physics 4, GPA 3.9, SAT 1520"
    "A-Level: 数学 A*, 物理 A, 化学 A, 雅思 7.0"
    "IB 总分 38 / 45，托福 105"
    "高考 642（省位次 3800）"
"""
from __future__ import annotations
import re
from typing import Dict, Tuple, List
from . import registry

# 各体系触发关键词（去空格/小写匹配）
_SYSTEM_KEYWORDS = {
    "AP": ["ap", "advanced placement", "ap课程", "ap考试", "先修",
           "collegeboard", "college board", "ap微积分", "ap化学", "ap物理"],
    "AL": ["a-level", "alevel", "a level", "al课程", "爱德思", "cie", "caie",
           "edexcel", "cambridge", "剑桥al", "as level", "a2"],
    "IB": ["ib ", "international baccalaureate", "ib课程", "国际文凭", "ib总分",
           " ib", "hl ", " sl ", "toefl ee"],
    "GAOKAO": ["gaokao", "高考", "gk ", "位次", "一本", "一段", "省排", "省排名"],
    "SAT": ["sat", "新sat", "老sat"],
    "TOEFL": ["toefl", "托福", "ibt"],
    "IELTS": ["ielts", "雅思"],
}

# 学科中文 → 体系线索
_SUBJECT_HINT = {
    "AP": ["微积分", "ap", "statistics", "化学", "物理", "生物", "经济"],
    "AL": ["as", "a2", "数学", "进阶数学", "高数", "经济", "物理", "化学", "生物",
           "会计", "商学"],
    "IB": ["hl", "sl", "toefl", "ee", "tok"],
}

_GRADE_RE = re.compile(r"(A\*|A|B|C|D|E|U)(?![a-z])", re.IGNORECASE)
_AP_SUBJ_RE = re.compile(r"\b(calc|calculus|chem|physics|bio|stats|statistics|computer\s?science)"
                         r"\s?(?:bc|ab|1|2|c|e&m|mech)?\s*[:：]?\s*([1-5])\b", re.IGNORECASE)
_AL_SUBJ_RE = re.compile(r"(?:数学|进阶数学|高数|物理|化学|生物|经济|会计|商学|further\s?math|maths?)"
                         r"\s*(?:[:：]\s*)?\s*((?:A\*|A|B|C|D|E|U))", re.IGNORECASE)
_IB_TOTAL_RE = re.compile(r"(?:ib\s*)?(?:总分|total)?\s*[:：]?\s*(3[0-9]|4[0-5]|2[4-9])\s*/\s*45", re.IGNORECASE)
_GK_TOTAL_RE = re.compile(r"高考?[:：]?\s*([3-7][0-9]{2})", re.IGNORECASE)
_SAT_TOTAL_RE = re.compile(r"(?:sat|新sat)[:：\s]*([1-2][0-9]{3})\b", re.IGNORECASE)
_TS_TOTAL_RE = re.compile(r"(?:托福|toefl|ibt)[:：\s]*([0-9]{2,3})\b", re.IGNORECASE)
_IL_TOTAL_RE = re.compile(r"(?:雅思|ielts)[:：\s]*([0-9](?:\.[0-9])?)\b", re.IGNORECASE)
_GK_RANK_RE = re.compile(r"(?:位次|排名|省排|rank)[:：\s]*([0-9,]+)", re.IGNORECASE)
_GPA_RE = re.compile(r"(?:gpa|g点)[:：\s]*([0-4](?:\.[0-9]+)?)", re.IGNORECASE)


class RecognitionResult:
    """识别结果。"""
    def __init__(self, system: str, confidence: float,
                 features: Dict[str, float], matched_keywords: List[str],
                 note: str = ""):
        self.system = system
        self.confidence = confidence
        self.features = features
        self.matched_keywords = matched_keywords
        self.note = note

    def __repr__(self):
        return (f"<RecognitionResult system={self.system} conf={self.confidence:.2f} "
                f"features={self.features}>")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower())


def recognize(text: str, context: str = "") -> RecognitionResult:
    """识别文本分数属于哪套体系。"""
    if not text or not text.strip():
        return RecognitionResult("OTHER", 0.0, {}, [], "空输入")

    nt = _norm(text)
    hits: Dict[str, int] = {}

    # 1) 显式体系关键词
    for sys_, kws in _SYSTEM_KEYWORDS.items():
        for kw in kws:
            if kw.strip() in nt:
                hits[sys_] = hits.get(sys_, 0) + 1

    # 2) 学科句式强线索
    # AP 单科模式 "Calc 5" / "物理 5"：能匹配 AP 数值
    if _AP_SUBJ_RE.search(text):
        hits["AP"] = hits.get("AP", 0) + 3
    # A-Level 字母等级 + 中文科目
    al_subj = _AL_SUBJ_RE.findall(text)
    if al_subj:
        hits["AL"] = hits.get("AL", 0) + 2
    # IB HL/SL 或 /45
    if _IB_TOTAL_RE.search(text) or re.search(r"\bHL\b|\bSL\b", text, re.IGNORECASE):
        hits["IB"] = hits.get("IB", 0) + 2

    # 3) 数值模式
    if _GK_TOTAL_RE.search(text):
        hits["GAOKAO"] = hits.get("GAOKAO", 0) + 3
    if _SAT_TOTAL_RE.search(text):
        hits["SAT"] = hits.get("SAT", 0) + 2
    if _TS_TOTAL_RE.search(text):
        hits["TOEFL"] = hits.get("TOEFL", 0) + 2
    if _IL_TOTAL_RE.search(text):
        hits["IELTS"] = hits.get("IELTS", 0) + 2

    # context 辅助
    if context:
        nh = _norm(context)
        for sys_, kws in _SYSTEM_KEYWORDS.items():
            if sys_ in ("AP", "AL", "IB", "GAOKAO"):
                if any(kw.strip() in nh for kw in kws):
                    hits[sys_] = hits.get(sys_, 0) + 1

    if not hits:
        return RecognitionResult("OTHER", 0.0, {}, [], "未匹配到已知体系特征")

    # 主体系 = 得票最高，但语言成绩(TOEFL/IELTS)不应盖过主体学科体系。
    # 先把语言类与非语言类分开看
    lang = {k: v for k, v in hits.items() if k in ("TOEFL", "IELTS")}
    non_lang = {k: v for k, v in hits.items() if k not in ("TOEFL", "IELTS")}
    if non_lang:
        best = max(non_lang, key=non_lang.get)
    elif lang:
        best = max(lang, key=lang.get)  # 只有语言分
    else:
        best = "OTHER"

    # 提取特征
    feats = _extract_features(text, best)

    total = sum(hits.values())
    confidence = min(1.0, hits.get(best, 0) / max(total, 1) + 0.15)
    confidence = min(1.0, confidence)

    return RecognitionResult(best, confidence, feats, list(hits.keys()), "")


def _extract_features(text: str, system: str) -> Dict[str, float]:
    """根据体系提取归一化特征。"""
    feats: Dict[str, float] = {}
    # 语言（所有体系都可带）
    tm = _TS_TOTAL_RE.search(text)
    if tm:
        feats["toefl"] = float(tm.group(1))
    im = _IL_TOTAL_RE.search(text)
    if im:
        try:
            feats["ielts"] = float(im.group(1))
        except ValueError:
            pass

    if system == "AP":
        ap_subs = _AP_SUBJ_RE.findall(text)
        nums = [int(b) for _, b in ap_subs]
        if not nums:
            # 兼容 "AP: X, X, X=5 无科目名" 情况
            nums = [int(x) for x in re.findall(r"\b([45])\b", text)
                    if int(x) in (4, 5)]
        if nums:
            feats["ap_subjects"] = float(len(nums))
            feats["ap_avg"] = float(sum(nums) / len(nums))
            feats["ap_top_ratio"] = float(sum(1 for x in nums if x == 5) / len(nums))
        gm = _GPA_RE.search(text)
        if gm:
            feats["gpa"] = float(gm.group(1))
        sm = _SAT_TOTAL_RE.search(text)
        if sm:
            feats["sat"] = float(sm.group(1))

    elif system == "AL":
        al_pairs = _AL_SUBJ_RE.findall(text)
        gmap = {"A*": 5, "A": 4, "B": 3, "C": 2, "D": 1, "E": 0.5, "U": 0}
        nums = []
        if al_pairs:
            for g in al_pairs:
                g = g.strip().upper()
                nums.append(gmap.get(g, 0))
        if not nums:
            for g in _GRADE_RE.findall(text):
                g = g.upper().replace("\\", "")
                nums.append(gmap.get(g, 0))
        if nums:
            feats["al_subjects"] = float(len(nums))
            feats["al_avg"] = float(sum(nums) / len(nums))
            feats["al_top_ratio"] = float(sum(1 for x in nums if x >= 4) / len(nums))

    elif system == "IB":
        im2 = _IB_TOTAL_RE.search(text)
        if im2:
            feats["ib_total"] = float(im2.group(1))

    elif system == "GAOKAO":
        gm2 = _GK_TOTAL_RE.search(text)
        if gm2:
            feats["gk_total"] = float(gm2.group(1))
        rm = _GK_RANK_RE.search(text)
        if rm:
            feats["gk_rank"] = float(rm.group(1).replace(",", ""))

    elif system == "SAT":
        sm = _SAT_TOTAL_RE.search(text)
        if sm:
            feats["sat"] = float(sm.group(1))
    elif system == "TOEFL":
        tm = _TS_TOTAL_RE.search(text)
        if tm:
            feats["toefl"] = float(tm.group(1))
    elif system == "IELTS":
        im = _IL_TOTAL_RE.search(text)
        if im:
            try:
                feats["ielts"] = float(im.group(1))
            except ValueError:
                pass
    return feats
