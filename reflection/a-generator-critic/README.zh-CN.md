# 生成批评

> 专栏第 **06-02** 讲 · 模式 · 反思行 × 链式列
> [English README](README.md)

## 模式契约

生成批评只审一份产出，只走一遍有界链：

```text
生成 -> 批评 -> 策略裁决 -> 可选的修订草稿
```

批评者负责报告问题和证据，没有放行权。确定性的 `AcceptancePolicy`
根据有证据的问题和有依据的分数，给被审产出作出 `ACCEPTED` 或
`NEEDS_REVISION` 裁决。修订器如生成新稿，这份新稿明确处于未复审状态，
必须由外层流程再次提交，才能获得新的裁决。

这条边界决定了它位于反思行、链式列。由 test、lint、build 或 CI 红灯
强制驱动、一直修到转绿或熔断的结构，属于相邻的
[自愈循环](../d-self-heal-loop/README.zh-CN.md)。

## 快速开始

```bash
python3 reflection/a-generator-critic/example.py
python3 reflection/payroll-lab/generator_critic_lab.py
python3 reflection/payroll-lab/generator_critic_lab.py --rubber-stamp
```

薪酬 Lab 中，月报声称 800 张工资单已支付，而 SQLite 里的事实是 798 张
`PAID`、2 张 `REVERSED`。标准批评者会挂接账本与 schema 证据，第一遍只
生成待复审的修订稿，第二遍显式提交后才可能放行。`--rubber-stamp`
移除这些外部事实，展示一位文风漂亮的批评者如何批准错误月报。

## 参考接口

[`pattern.py`](pattern.py) 把四项责任拆开：

- `Critique` 保存批评意见与证据。
- `AcceptancePolicy` 独占放行裁决。
- `ChainResult.reviewed_artifact` 指明本遍真正审过的对象。
- `ChainResult.revision_draft` 在下一遍显式复审前始终是草稿。

运行不变量测试：

```bash
uv run pytest reflection/a-generator-critic/test_pattern.py -q
```

## 矩阵位置

这个模式坐落在 **反思 × 链式** 的交点。相邻模式见
[双轴矩阵](../../README.zh-CN.md#28-个模式的矩阵)。
