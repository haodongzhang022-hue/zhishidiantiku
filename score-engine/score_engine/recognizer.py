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
           "collegeboard", "college board", "ap微积分", "ap化学", "ap物理",
           "ap生物", "ap经济", "ap统计", "ap计算机"],
    "AL": ["a-level", "alevel", "a level", "al课程", "爱德思", "cie", "caie",
           "edexcel", "cambridge", "剑桥al", "as level", "a2", "a*", "alevel课程"],
    "IB": ["ib ", "international baccalaureate", "ib课程", "国际文凭", "ib总分",
           " ib", "hl ", " sl ", "toefl ee", "ib文凭"],
    "GAOKAO": ["gaokao", "高考", "gk ", "位次", "一本", "一段", "省排", "省排名",
               "国内高考"],
    "SAT": ["sat", "新sat", "老sat"],
    "TOEFL": ["toefl", "托福", "ibt"],
    "IELTS": ["ielts", "雅思"],
}

# 主体学科体系：这些体系如果被明确识别到，SAT/TOEFL/IELTS 只能作为附属成绩
# 不能盖过主体体系成为主判。
_MAIN_SYSTEMS = ("AP", "AL", "IB", "GAOKAO")

# 附属成绩体系（语言类 + SAT 标化）：
# 只有当文本中没有主体学科体系时，它们才可能成为主体系。
_ANCILLARY_SYSTEMS = ("SAT", "TOEFL", "IELTS")

# 学科中文 → 体系线索
_SUBJECT_HINT = {
    "AP": ["微积分", "ap", "statistics", "化学", "物理", "生物", "经济",
           "统计", "计算机"],
    "AL": ["as", "a2", "数学", "进阶数学", "高数", "经济", "物理", "化学", "生物",
           "会计", "商学"],
    "IB": ["hl", "sl", "toefl", "ee", "tok"],
}

_GRADE_RE = re.compile(r"(A\*|A|B|C|D|E|U)(?![a-z])", re.IGNORECASE)

# AP 科目正则：英文科目名（含 AP 科目代码如 BC/AB/C/E&M）+ 中文科目名
# 注意：中文 AP 科目后可直接接数字（如"化学5"），无需空格。
_AP_SUBJ_RE = re.compile(
    r"(?:"
    # 英文 AP 科目
    r"(?:calc|calculus)\s*(?:bc|ab|1|2)?|"          # Calculus BC/AB
    r"(?:chem|chemistry)|"                          # Chemistry
    r"(?:physics)\s*(?:1|2|c|e&m|mech|ab|bc)?|"     # Physics C/1/2
    r"(?:bio|biology)|"                             # Biology
    r"(?:stats|statistics)|"                        # Statistics
    r"(?:computer\s?science|cs)|"                   # CS
    r"(?:econ(?:omics)?)|"                          # Economics
    r"(?:english|lang|literature|lit)|"             # English/Lang/Lit
    r"(?:psychology|psych)|"                        # Psychology
    r"(?:环境科学|env\s?science)|"                    # Env Sci
    r"(?:gov\s?(?:&|\band)\s?politics|ap\s?gov)|"   # Gov
    # 中文 AP 科目
    r"(?:微积分)\s*(?:bc|ab)?|"                      # 微积分 BC/AB
    r"(?:化学)|"
    r"(?:物理)\s*(?:c|1|2|ab|bc|e&m)?|"              # 物理C / 物理1 / 物理2
    r"(?:生物)|"
    r"(?:统计(?:学)?)|"
    r"(?:计算机(?:科学)?)|"
    r"(?:经济学|经济)|"
    r"(?:心理学)|"
    r"(?:环境科学)|"
    r"(?:英语(?:语言)?|英语文学)"
    r")"
    # 数字分数（5/4/3/2/1）
    r"\s*[:：]?\s*([1-5])\b", re.IGNORECASE)

# A-Level 科目 + 等级字母：要求等级字母独立出现在科目后，且前面不是数字/字母紧跟。
# 关键改进：当等级字母与 AP 科目代码(如 "物理C" 中的 C) 混在一起时
# 会误判——用 negative lookbehind 排除紧跟字母/数字的情况。
# 同时科目名和等级字母之间需要有分隔（空格/冒号/顿号/逗号等）或用括号明确等级。
_AL_SUBJ_RE = re.compile(
    r"(?:"
    # 英文 A-Level 科目
    r"(?:further\s?math|maths?|math)|"
    # 中文 A-Level 科目
    r"(?:数学|进阶数学|高数|物理|化学|生物|经济(?:学)?|会计|商学|计算机(?:科学)?|中文|心理学)"
    r")"
    # 科目名后必须跟分隔或独立边界
    r"\s*(?:[:：,，、\s]*)\s*"
    r"((?:A\*|A|B|C|D|E|U)(?![a-z0-9]))",
    re.IGNORECASE)

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
    # AP 单科模式 "Calc 5" / "物理 5" / "化学5" / "微积分BC 5"：匹配 AP 数值
    ap_subj_matches = _AP_SUBJ_RE.findall(text)
    if ap_subj_matches:
        # 每个 AP 科目得分 +1，最多算 3 个
        hits["AP"] = hits.get("AP", 0) + min(len(ap_subj_matches), 3)

    # A-Level 字母等级 + 科目（仅在无 AP 上下文时有较高权重）
    al_subj = _AL_SUBJ_RE.findall(text)
    has_ap_ctx = "ap" in nt or "ap微积分" in nt or "ap化学" in nt or "ap物理" in nt \
        or "advanced placement" in nt
    if al_subj and not has_ap_ctx:
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
            if sys_ in _MAIN_SYSTEMS:
                if any(kw.strip() in nh for kw in kws):
                    hits[sys_] = hits.get(sys_, 0) + 1

    if not hits:
        return RecognitionResult("OTHER", 0.0, {}, [], "未匹配到已知体系特征")

    # 4) 主体系判定
    # 将体系分为"主体学科体系"和"附属成绩体系"
    main_hits = {k: v for k, v in hits.items() if k in _MAIN_SYSTEMS}
    anc_hits = {k: v for k, v in hits.items() if k in _ANCILLARY_SYSTEMS}

    if main_hits:
        # 有主体学科体系时，附属成绩只补充特征，不作为主体系
        best = max(main_hits, key=main_hits.get)
    elif anc_hits:
        # 没有主体学科体系，附属成绩可以成为主体系（如纯 SAT 考生）
        best = max(anc_hits, key=anc_hits.get)
    else:
        best = "OTHER"

    # 提取特征（用最佳体系，同时也提取文本中所有语言成绩特征）
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

    # SAT 标化（AP/AL/IB 等主体体系也可附带）
    sm = _SAT_TOTAL_RE.search(text)
    if sm:
        feats["sat"] = float(sm.group(1))

    if system == "AP":
        ap_subs = _AP_SUBJ_RE.findall(text)
        nums = [int(b) for b in ap_subs]
        if not nums:
            # 兼容 "AP: X, X, X=5 无科目名" 情况
            nums = [int(x) for x in re.findall(r"(?<![0-9])([45])(?![0-9])", text)
                    if int(x) in (4, 5)]
        if nums:
            feats["ap_subjects"] = float(len(nums))
            feats["ap_avg"] = float(sum(nums) / len(nums))
            feats["ap_top_ratio"] = float(sum(1 for x in nums if x == 5) / len(nums))
        gm = _GPA_RE.search(text)
        if gm:
            feats["gpa"] = float(gm.group(1))

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
        # SAT 分数已在上方统一提取
        pass
    elif system == "TOEFL":
        # TOEFL 分数已在上方统一提取
        pass
    elif system == "IELTS":
        # IELTS 分数已在上方统一提取
        pass
    return feats
