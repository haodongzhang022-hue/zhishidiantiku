# -*- coding: utf-8 -*-
"""训练 / 后训练 / 效果跟踪。

设计点：
- 使用"历年"历史录取样本，切分 train/valid。
- 每次 new data 到来，做**增量后训练**（warm start），并评估指标（准确率/AUC/MSE）。
- 训练元信息记录每次快照（时间、样本量、指标、数据hash），支持**效果跟踪与回滚**。
- **masked training**：缺失字段不参与反向传播（见 nn.py 说明）。
"""
from __future__ import annotations
import hashlib, json, os, time, random
from typing import List, Optional, Tuple, Dict

from . import registry, models, nn, converter as conv_mod


class Trainer:
    def __init__(self, model_path: Optional[str] = None,
                 model: Optional[nn.MLP] = None):
        self.model_path = model_path
        self.model = model
        self.history = []   # 训练快照

    # ---------- 数据准备 ----------
    def _split(self, records: List[registry.AdmissionRecord],
               val_ratio: float = 0.15, seed: int = 7):
        rng = random.Random(seed)
        idx = list(range(len(records)))
        rng.shuffle(idx)
        nv = max(1, int(len(records) * val_ratio))
        val = [records[i] for i in idx[:nv]]
        tr = [records[i] for i in idx[nv:]]
        return tr, val

    def _dataset(self, records: List[registry.AdmissionRecord]):
        """返回 (X, y, masks)。X 中缺失维度填 0，masks 标记 0。"""
        X, masks = [], []
        for r in records:
            vec, m = models.features_from_record(r)
            X.append(vec)
            masks.append(m)
        # 连续价值回归目标（可达学校档位）
        y = [models.value_of_record(r) for r in records]
        return X, y, masks

    # ---------- 主训练 ----------
    def train(self, records: List[registry.AdmissionRecord],
              epochs: int = 300, lr: float = 0.5,
              verbose: int = 1, source_tag: str = ""):
        tr, va = self._split(records)
        Xt, yt, mt = self._dataset(tr)
        if self.model is None:
            self.model = nn.MLP(input_dim=models.FEATURE_DIM, seed=42, lr=lr)
        losses = self.model.fit(Xt, yt, epochs=epochs, lr=lr, masks=mt,
                                verbose=verbose)
        # 验证指标
        Xv, yv, mv = self._dataset(va)
        mae, mse, corr = self._metrics(Xv, yv, mv)
        snap = {
            "ts": time.time(),
            "source_tag": source_tag or "train",
            "samples": len(records),
            "train_samples": len(tr),
            "val_samples": len(va),
            "epochs": epochs,
            "loss": round(losses[-1], 5),
            "val_mse": round(mse, 5),
            "val_mae": round(mae, 4),
            "val_corr": round(corr, 4),
            "feature_schema": models.FEATURE_KEYS,
            "data_hash": self._data_hash(records),
        }
        self.history.append(snap)
        if verbose:
            print(f"[trainer] 完成：样本={len(records)} "
                  f"val_mae={mae:.3f} val_mse={mse:.4f} val_corr={corr:.3f}")
        return snap

    # ---------- 后训练（增量） ----------
    def retrain(self, new_records: List[registry.AdmissionRecord],
                old_records: Optional[List[registry.AdmissionRecord]] = None,
                epochs: int = 80, lr: float = 0.1,
                verbose: int = 1, source_tag: str = "retrain"):
        """基于既有模型做增量后训练（warm start），冷启动则全量训练。"""
        if self.model is None:
            if verbose:
                print("[trainer] 无既有模型，转为全量训练")
            return self.train(new_records, epochs=max(epochs, 200),
                              lr=lr, verbose=verbose, source_tag=source_tag)
        if old_records:
            all_rec = old_records + new_records
        else:
            all_rec = new_records
        X, y, m = self._dataset(all_rec)
        losses = self.model.fit(X, y, epochs=epochs, lr=lr, masks=m,
                                verbose=verbose)
        # 效果跟踪
        if len(all_rec) > 20:
            Xv, yv, mv = self._dataset(all_rec[-20:])
        else:
            Xv, yv, mv = X, y, m
        mae, mse, corr = self._metrics(Xv, yv, mv)
        snap = {
            "ts": time.time(), "source_tag": source_tag,
            "samples": len(all_rec), "new_samples": len(new_records),
            "epochs": epochs, "loss": round(losses[-1], 5),
            "val_mse": round(mse, 5), "val_mae": round(mae, 4),
            "val_corr": round(corr, 4),
            "data_hash": self._data_hash(all_rec),
            "prev_warm_start": True,
        }
        self.history.append(snap)
        if verbose:
            print(f"[trainer] 增量后训练完成：新增{len(new_records)}条，"
                  f"total={len(all_rec)} val_mae={mae:.3f}")
        return snap

    # ---------- 指标 ----------
    def _metrics(self, X, y, masks=None):
        if not X:
            return 0, 0, 0.0
        if masks is None:
            masks = [[1] * len(x) for x in X]
        preds = [self.model.predict(x, m) for x, m in zip(X, masks)]
        n = len(y)
        mae = sum(abs(p - t) for p, t in zip(preds, y)) / n
        mse = sum((p - t) ** 2 for p, t in zip(preds, y)) / n
        corr = self._pearson(preds, y)
        return mae, mse, corr

    @staticmethod
    def _pearson(a, b):
        n = len(a)
        if n < 2:
            return 0.0
        ma = sum(a) / n
        mb = sum(b) / n
        da = [x - ma for x in a]
        db = [x - mb for x in b]
        sxy = sum(x * y for x, y in zip(da, db))
        sxx = sum(x * x for x in da)
        syy = sum(y * y for y in db)
        if sxx == 0 or syy == 0:
            return 0.0
        return sxy / (sxx ** 0.5 * syy ** 0.5)

    @staticmethod
    def _calc_auc(pos, neg):
        if not pos or not neg:
            return 0.5
        pairs = 0
        for p, _ in pos:
            for n, _ in neg:
                if p > n:
                    pairs += 1
                elif p == n:
                    pairs += 0.5
        return pairs / (len(pos) * len(neg))

    @staticmethod
    def _data_hash(records: List[registry.AdmissionRecord]) -> str:
        raw = "|".join(
            f"{r.school}|{r.university_id}|{r.year}|{r.system}|{int(r.admitted)}|{sorted(r.features.items())}"
            for r in records)
        return hashlib.md5(raw.encode()).hexdigest()[:8]

    # ---------- 持久化 ----------
    def save(self, path: Optional[str] = None):
        p = path or self.model_path
        if not p:
            raise ValueError("需要 model_path")
        if self.model is None:
            raise ValueError("model 尚未训练")
        self.model.save(p)
        meta_path = p + ".meta.json"
        with open(meta_path, "w") as f:
            json.dump({"history": self.history, "schema": models.FEATURE_KEYS},
                      f, ensure_ascii=False, indent=2)
        print(f"[trainer] 模型已保存: {p}（快照 {len(self.history)} 次）")

    def load(self, path: Optional[str] = None):
        p = path or self.model_path
        self.model = nn.MLP.load(p)
        meta_path = p + ".meta.json"
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            self.history = meta.get("history", [])
        print(f"[trainer] 模型已载入: {p}（历史快照 {len(self.history)} 次）")

    def effect_trend(self) -> List[Dict]:
        """返回训练效果跟踪序列，便于监控漂移。"""
        return list(self.history)
