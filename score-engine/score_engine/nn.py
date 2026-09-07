# -*- coding: utf-8 -*-
"""轻量多层感知机（MLP）——纯标准库实现。

用于把"多体系分数特征 → 统一录取价值(0~1)"的回归学习。
内置标准反传（backprop）+ 小批量 SGD；默认纯 Python，无第三方硬依赖。

**Masked training（新增）**：
用户指出缺失信息不应被 -1 误导为"学生弱"。为解决此问题：
- 输入特征向量中缺失维度填 0.0（对 sigmoid 中性）。
- 同时传入 mask（0/1），在反向传播时**缺失维度的梯度不更新权重**，
  即模型不会从"缺失"中学到"弱"或任何信号。
- mask 同时可用于前向时把缺失维度的权重贡献置零（缺失输入对中间层无贡献）。

用法：
    x = [0.5, 0.0, 0.8]       # 维度1缺失 → 填 0
    m = [1, 0, 1]             # mask: 维度1缺失
    model.fit(X, y, masks=masks)
    model.predict(x, mask=m)
"""
from __future__ import annotations
import math, json, random, os
from typing import List, Optional


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class MLP:
    """简单前馈网络，输出层用 sigmoid 挤压到 0~1（当作回归/概率）。

    支持 mask：输入缺失维度填 0 但 mask 为 0，前向时该输入贡献为 0，
    反向时不更新该维度对应权重（避免学成"缺失=弱"）。
    """
    def __init__(self, input_dim: int, hidden: Optional[List[int]] = None,
                 seed: Optional[int] = None, lr: float = 0.5):
        if hidden is None:
            hidden = [8, 4]
        self.lr = lr
        self.input_dim = input_dim
        self.seed = seed
        self.shape = [input_dim] + list(hidden) + [1]
        rng = random.Random(seed)
        self.ws = []
        self.bs = []
        for i in range(len(self.shape) - 1):
            fan_in, fan_out = self.shape[i], self.shape[i + 1]
            bound = math.sqrt(6.0 / (fan_in + fan_out))
            w = [[rng.uniform(-bound, bound) for _ in range(fan_out)]
                 for _ in range(fan_in)]
            b = [0.0] * fan_out
            self.ws.append(w)
            self.bs.append(b)

    def predict(self, x: List[float], mask: Optional[List[int]] = None) -> float:
        """前向得到输出（0~1）。

        mask: 长度 input_dim 的 0/1 列表。缺失维度（mask=0）的输入值应填 0，
        其权重在前向贡献中被掩蔽。
        """
        # mask 存在时：把 mask=0 的输入维度归零
        a = list(x)
        if mask is not None:
            assert len(mask) == len(x), "mask length must match input"
            a = [v if m else 0.0 for v, m in zip(a, mask)]
        for i in range(len(self.ws)):
            net = [self.bs[i][j] +
                   sum(a[k] * self.ws[i][k][j] for k in range(len(a)))
                   for j in range(len(self.ws[i][0]))]
            a = [_sigmoid(v) for v in net]
        return a[0]

    def _forward_all(self, x: List[float], mask: Optional[List[int]] = None):
        """返回每层 pre-activation(net) 和 activation(a) 列表（含输入层）。"""
        nets = []
        a0 = list(x)
        if mask is not None:
            a0 = [v if m else 0.0 for v, m in zip(a0, mask)]
        acts = [a0]
        a = a0
        for i in range(len(self.ws)):
            net = [self.bs[i][j] +
                   sum(a[k] * self.ws[i][k][j] for k in range(len(a)))
                   for j in range(len(self.ws[i][0]))]
            nets.append(net)
            a = [_sigmoid(v) for v in net]
            acts.append(a)
        return nets, acts

    def _backward_one(self, x: List[float], y: float,
                      mask: Optional[List[int]] = None):
        """单样本后向更新（标准反传）。

        mask: 输入掩码。缺失维度（mask=0）对应第一层权重**不更新**。
        """
        nets, acts = self._forward_all(x, mask)
        L = len(self.ws)
        out = acts[-1][0]
        delta_next = [(out - y) * out * (1 - out)]
        deltas = [None] * L
        deltas[-1] = delta_next

        for l in range(L - 2, -1, -1):
            nxt_d = deltas[l + 1]
            w_next = self.ws[l + 1]
            out_l = acts[l + 1]
            d = []
            for j in range(len(out_l)):
                s = sum(w_next[j][m] * nxt_d[m] for m in range(len(nxt_d)))
                d.append(s * out_l[j] * (1 - out_l[j]))
            deltas[l] = d

        # 更新权重
        for l in range(L):
            a_in = acts[l]
            d = deltas[l]
            for i in range(len(a_in)):
                # 第一层缺失维度：mask[i]=0 → 不更新
                if l == 0 and mask is not None and not mask[i]:
                    continue
                for j in range(len(d)):
                    self.ws[l][i][j] -= self.lr * a_in[i] * d[j]
            for j in range(len(d)):
                self.bs[l][j] -= self.lr * d[j]

    def fit(self, X: List[List[float]], y: List[float],
            epochs: int = 300, lr: float = None,
            masks: Optional[List[List[int]]] = None,
            verbose: int = 0) -> List[float]:
        """训练。

        X: 特征向量（缺失维度填 0）。
        y: 目标。
        masks: 与 X 同长同维的 0/1 列表。None 表示所有维度均存在。
        """
        if lr is not None:
            self.lr = lr
        n = len(X)
        if masks is None:
            masks = [[1] * len(X[i]) for i in range(n)]
        losses = []
        for ep in range(epochs):
            idx = list(range(n))
            random.shuffle(idx)
            total = 0.0
            for i in idx:
                p = self.predict(X[i], masks[i])
                err = p - y[i]
                total += err * err
                self._backward_one(X[i], y[i], masks[i])
            avg = total / n
            losses.append(avg)
            if verbose and (ep % 25 == 0 or ep == epochs - 1):
                print(f"  epoch {ep}/{epochs}  MSE={avg:.5f}")
        return losses

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        obj = {
            "input_dim": self.input_dim,
            "lr": self.lr,
            "seed": self.seed,
            "shape": self.shape,
            "w": self.ws,
            "b": self.bs,
            "_ver": "mlp-masked-3"
        }
        with open(path, "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, path: str) -> "MLP":
        with open(path) as f:
            obj = json.load(f)
        m = cls.__new__(cls)
        m.input_dim = obj["input_dim"]
        m.lr = obj["lr"]
        m.seed = obj["seed"]
        m.shape = obj["shape"]
        m.ws = obj["w"]
        m.bs = obj["b"]
        return m
