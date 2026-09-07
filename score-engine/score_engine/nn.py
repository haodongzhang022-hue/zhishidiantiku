# -*- coding: utf-8 -*-
"""轻量多层感知机（MLP）——纯标准库实现。

用于把"多体系分数特征 → 统一录取价值(0~1)"的回归学习。
内置标准反传（backprop）+ 小批量 SGD；默认纯 Python，无第三方硬依赖。
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

    architecture: input_dim -> h1 -> h2 -> 1
    反向传播使用 MSE 目标，激活均为 sigmoid。
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
        # self.ws[l] 是 shape[l] x shape[l+1] 的权重，self.bs[l] 长度 shape[l+1]
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

    def predict(self, x: List[float]) -> float:
        """前向得到输出（0~1）。"""
        a = list(x)
        for i in range(len(self.ws)):
            net = [self.bs[i][j] +
                   sum(a[k] * self.ws[i][k][j] for k in range(len(a)))
                   for j in range(len(self.ws[i][0]))]
            a = [_sigmoid(v) for v in net]
        return a[0]

    def _forward_all(self, x: List[float]):
        """返回每层 pre-activation(net) 和 activation(a) 列表（含输入层）。"""
        nets = []
        acts = [list(x)]
        a = list(x)
        for i in range(len(self.ws)):
            net = [self.bs[i][j] +
                   sum(a[k] * self.ws[i][k][j] for k in range(len(a)))
                   for j in range(len(self.ws[i][0]))]
            nets.append(net)
            a = [_sigmoid(v) for v in net]
            acts.append(a)
        return nets, acts

    def _backward_one(self, x: List[float], y: float):
        """单样本后向更新（标准反传）。"""
        nets, acts = self._forward_all(x)
        L = len(self.ws)               # 层数
        # 输出层误差
        out = acts[-1][0]
        # MSE 损失 L = 0.5*(out-y)^2; 对输出 net 的导数 = (out-y)*sigmoid'(net)
        # sigmoid'(net)=out*(1-out)
        delta_next = [(out - y) * out * (1 - out)]   # 长度 1
        deltas = [None] * L
        # 输出层 delta
        deltas[-1] = delta_next

        # 从倒数第二层往回
        for l in range(L - 2, -1, -1):
            # delta[l] = (W_{l+1} . delta[l+1]) * h_l*(1-h_l)
            # 其中 h_l = acts[l+1]（本层输出作为下一层输入），net 导数需 sigmoid'
            nxt_d = deltas[l + 1]       # 长度 shape[l+2]
            w_next = self.ws[l + 1]     # shape[l+1] x shape[l+2]
            out_l = acts[l + 1]         # 本层输出，长度 shape[l+1]
            d = []
            for j in range(len(out_l)):
                s = sum(w_next[j][m] * nxt_d[m] for m in range(len(nxt_d)))
                d.append(s * out_l[j] * (1 - out_l[j]))
            deltas[l] = d

        # 更新：w[i][j] -= lr * a_in[i] * delta_out[j]
        for l in range(L):
            a_in = acts[l]            # 输入到本层
            d = deltas[l]             # 本层输出侧误差
            for i in range(len(a_in)):
                for j in range(len(d)):
                    self.ws[l][i][j] -= self.lr * a_in[i] * d[j]
            for j in range(len(d)):
                self.bs[l][j] -= self.lr * d[j]

    def fit(self, X: List[List[float]], y: List[float],
            epochs: int = 300, lr: float = None, verbose: int = 0) -> List[float]:
        if lr is not None:
            self.lr = lr
        n = len(X)
        losses = []
        for ep in range(epochs):
            idx = list(range(n))
            random.shuffle(idx)
            total = 0.0
            for i in idx:
                p = self.predict(X[i])
                err = p - y[i]
                total += err * err
                self._backward_one(X[i], y[i])
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
            "_ver": "mlp-2"
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
