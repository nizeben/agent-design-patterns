# 版本地图：这个案例是怎么长出来的

这份说明给专栏作者和读者一个公开版时间线。它只描述工程演化，不保留原始机构、地域、文件名和内部沟通信息。

## v0.1：Regulatory Schema

**输入**：一份金融产品披露类规范，以及一个“宣传材料是否合规”的业务场景。

**输出**：最小数据结构。

这一版的重点不是 benchmark，而是把下游接口讲清楚：

```text
source document
  -> reviewed checklist rules
  -> product promotion claims
  -> compliance findings
  -> review memo + audit trail
```

这一版产出的核心是 12 条 starter rules 和 JSON schema。它回答的问题是：下游检测模块到底应该消费什么。

## v0.2：Technical Slices

**输入**：schema、starter rules、样例 claim、早期 notebook。

**输出**：几页技术切片。

这一版的作用是把工程结构画出来：PDF 解析、候选规则、schema、finding、audit event 怎么接起来。它适合给技术负责人解释“这个模块在系统里的位置”。

## v0.3：Pattern Benchmark

**输入**：12 条 reviewed rules，普通模型输出，6 条模式路径。

**输出**：benchmark results、per-pattern notebooks、模式选型解释。

这一版开始回答第 09 模块真正关心的问题：面对同一个规则抽取任务，为什么要从单次生成走向组合策略。

关键数字：

| 路径 | 命中 |
|---|---:|
| single pass | 6 / 12 |
| critique repair | 7 / 12 |
| iterative self-refine | 7 / 12 |
| candidate-guided review | 9 / 12 |
| coverage-preserving union queue | 10 / 12 |
| consensus refine | 8 / 12 |

这个结果很适合讲“组合-集成之美”。组合策略不是为了让图复杂，而是为了让不同策略补不同的漏点。最高分来自 review queue，不是来自最像最终答案的那一版。

## v1.0：Public Column Case

**输入**：v0.3 的工程结构和得分。

**输出**：公开可发布的匿名案例。

脱敏处理包括：

* 原始机构名称移除。
* 原始地域线索移除。
* 原始文件名和 PDF 文本移除。
* 内部会议、汇报对象和路径移除。
* 只保留抽象后的规则类别、模式路径、分数和 harness。

公开版放在这个目录：`composition/d-checklist-benchmark/`。

它在专栏里的位置，应该放在 09-01 和 09-02 之后，当作一个“Pattern Selection Card 真跑出来是什么样”的案例。
