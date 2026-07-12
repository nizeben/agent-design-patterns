# 生成-批评

> 专栏第 **06-02** 讲 · 模式 · 反思行 × Chain列
> [English README](README.md)

## 状态

pattern.py 已落地（跟随极客时间《Agent 设计模式之美》第 27 讲 / 06-02）。核心判断：**批评者的成色取决于接进来的外部信号**，且 no-changes-needed 必须是合法裁决。有界链（默认 3 轮，学 Aider base_coder.py 的硬编码上限），带证据闸（无证据的批评意见只记录、不触发修订）。

## 快速开始

```bash
cd ../payroll-lab
python3 generator_critic_lab.py            # 三场景：接信号的批评链 / 橡皮图章 / --stubborn 轮次耗尽交人工
```

## 矩阵位置

这个模式坐落在 **反思（认知功能）× Chain（执行拓扑）** 的交点。
跟邻居模式的关系见
[双轴矩阵](../../README.zh-CN.md#28-个模式的矩阵)。

## 这个模式讲什么

工作标题：**生成-批评**（英文：Generator-Critic）。完整内容见 Manning *Designing
AI Agents* 第 06 章和极客时间专栏。
