# 09-04｜组合案例：从规则抽取到高召回审阅队列-Codex v1

你好，我是黄佳。前面两讲，我们讲了 Pattern Selection Card 和六步选型法。今天这篇是一个补充案例，专门回答一个更落地的问题：当你真的面对一份几十页的业务规范，想让 Agent 抽成可执行 checklist 时，组合模式到底有没有用？

我先说结论。这个案例里，单次生成只命中 12 条标准规则里的 6 条。加入生成-批评和自我修正后，能到 7 条。引入候选队列后，能到 9 条。最后，把多条路径的结果保留下来，形成高召回审阅队列，可以到 10 条。

这个结果很适合放在 09 模块里。它的重点不在模型越来越聪明，而在架构师怎么把不稳定输出变成可审阅流程。

## 先把旧版本说清楚

这几天围绕这个案例，其实已经长出了好几个版本。它们并列存在，服务于不同阶段。

第一版是 **schema 版**。它的任务很朴素：先把业务规范翻译成机器能消费的数据结构。输入是一份金融产品披露类规范，输出是 12 条 starter rules、rule schema、claim-to-finding 的数据契约。这个版本回答的是“下游系统到底吃什么”。

第二版是 **technical slices 版**。它把 schema、候选规则、检测结果、人工审核、审计事件画成几页技术图。这个版本的用途，是让技术负责人一眼看懂模块边界：哪一步负责抽取，哪一步负责检测，哪一步需要人工审核。

第三版是 **benchmark 版**。这一版开始真正进入第 09 模块：我们拿 12 条人工审阅过的规则作为 Golden Rules，让普通模型用不同模式去抽取，再统一打分。这个版本回答的是“为什么不能只让模型抽一次”。

现在这篇 **Codex v1** 是公开专栏版。它会保留工程结构和实验结果，但拿掉原始机构、地域、文件名、内部会议和汇报语境。读者看到的是一个匿名的金融产品披露 checklist benchmark，不会看到某个具体监管文件的复盘。

这个处理很重要。真实案例有力量，但专栏里要讲的是可复用的设计方法。具体项目本身只做背景，不进入正文。

## 任务：把一份规范变成 checklist

这个案例的业务任务可以这样抽象：

```text
long-form source standard
  -> candidate clauses
  -> reviewed golden checklist
  -> model-generated checklist
  -> score + review queue
  -> human-approved checklist
```

这里的 deliverable 是 checklist。Schema 只是数据契约，规定每条规则要有 `source`、`category`、`predicate`、`requirement`、`severity` 等字段。真正给下游检测模块使用的，是那 12 条经过审阅的规则。

这 12 条规则里，11 条来自披露质量相关章节，1 条来自目标客群适配相关章节。为什么要多放这一条？因为如果测试集全是同一类 disclosure 规则，模型容易靠惯性猜中。加一条 target-segment suitability，可以检验它有没有真的看见任务边界。

## 第一轮：普通模型能到哪里

我们先不用复杂架构，只做一次普通抽取：

```text
source bundle + checklist schema
  -> model call
  -> predicted checklist
  -> score against 12 golden rules
```

结果是 `6 / 12`。

这个分数并不奇怪。普通模型读长文档时，往往会抓住显眼条款，漏掉边角条款。它也容易把多个义务合并成一句漂亮的话。人读起来顺，机器评分时就丢了，因为 checklist 要的是“可检查的原子规则”。

所以第一轮给我们的东西叫 baseline。它告诉我们：如果只靠一次生成，这个任务大概就是一半覆盖。

## 第二轮：反思模式能修多少

接下来加 Reflection。

第一条路径是 `critique_repair`：先生成一版，再让模型对照 source 和 schema 做批评修复。第二条路径是 `iterative_self_refine`：让模型多轮自我修正。

结果很接近：

| 路径 | 双轴位置 | 命中 |
|---|---|---:|
| `critique_repair` | Reflection × Chain | 7 / 12 |
| `iterative_self_refine` | Reflection × Loop | 7 / 12 |

这说明反思有用，但在这个任务里不能神化。它能修掉一些明显遗漏和字段问题，却不一定能发现所有没被初稿覆盖的条款。原因也很简单：如果初稿没有把某个条款放进候选空间，后面的自我批评也可能围着已有答案打转。

这就是很多 Agent 项目会踩的坑：以为“多想几轮”就一定更好。实际工程里，循环只能提高局部质量，不能自动保证全局覆盖。

## 第三轮：候选队列把问题变成审阅

真正的变化出现在 Governance × Route。

我们先用确定性程序从文档里切出候选条款，再让模型做“晋级”：

```text
source standard
  -> deterministic candidate extractor
  -> candidate queue
  -> model promotes / edits / merges / rejects
  -> reviewed checklist draft
```

这一路的结果是 `9 / 12`。

为什么提升明显？因为任务形态变了。前两轮让模型“凭理解写 checklist”，这一轮让模型“从候选队列里做审阅”。审阅比凭空生成更适合合规场景。候选条款把搜索空间摊开，模型不容易完全漏掉某个角落。

这里的 Governance 不是把正确答案给模型看。Governance 指的是：候选队列、schema gate、score evidence、人工审核路径。它给系统加的是审计结构，不是答案泄露。

## 第四轮：组合策略为什么赢

最后一步，我们把多个路径的结果保留下来，不急着压缩成最终 checklist。

```text
single pass draft
critique repair draft
self-refine draft
candidate-guided draft
  -> union by source/category
  -> preserve complementary coverage
  -> human review queue
```

这条 `coverage_preserving_union_queue` 路径拿到了 `10 / 12`。

它的 predicted item 数量更多，precision 没有最高，但 recall 最高。对生产系统来说，这反而是合理的。因为这个阶段不是最终发布 checklist，而是给人审的候选队列。宁可多给审阅者几个可删的候选，也不要在自动压缩阶段把重要规则藏掉。

我们也跑了一个 `orchestrated_consensus_refine`，也就是先合并多路结果，再压缩成更像最终清单的一版。结果是 `8 / 12`。它比 baseline 好，但比高召回队列差。

这个对比很关键。它说明“最终答案更整齐”不等于“工程效果更好”。在有人工审核的流程里，最有价值的中间产物常常不是 final answer，而是 review queue。

## 用 Pattern Selection Card 复盘

现在回到第 09 模块的方法论。这个案例的 Pattern Selection Card 可以这样填：

| 步骤 | 选择 |
|---|---|
| ASSESS | 长文档、schema 输出、覆盖风险、人工审核、证据追踪 |
| ROUTE | Reasoning × Chain 做 baseline，Reflection 做修复，Governance × Route 做候选队列，Parallel -> Route 做高召回组合 |
| SELECT | 跑 6 条路径，比较覆盖率、可审阅性和压缩损失 |

如果只看单个模式，你可能会说：“那就用生成-批评吧。”但一旦进入组合视角，答案变了：先用 baseline 确定难度，再用 candidate-guided review 拉高覆盖，再用 union queue 保留互补候选，最后交给人工审核。

这就是 Composition 的价值：把不同模式放在不同阶段，让它们各自暴露一种信息。

## 这个案例能给读者什么

读者读完这个案例，应该拿走三件事。

第一，**Golden Rules 要先有**。没有标准答案，你无法判断模式有没有变好。很多 Agent 项目的问题，常常出在根本没有可评分的目标。

第二，**单次生成只是 baseline**。它很适合快速试水，但不要把 baseline 当架构。baseline 的价值是让你知道任务难在哪里。

第三，**高召回队列是合规类任务的好中间态**。在需要人工审核的场景里，保留候选比过早收敛更重要。最终 checklist 可以晚一点定，但审阅证据不能丢。

这也解释了为什么这个案例应该放在 09 模块，而不是单独放进某个 Reasoning 或 Reflection 模式。它的核心落在多个格子的协作关系上。

## 总结一下

这个匿名 checklist benchmark，把第 09 模块的抽象方法落到了一个可测量案例上。

```text
single pass                  -> 6 / 12
critique repair              -> 7 / 12
iterative self-refine         -> 7 / 12
candidate-guided review      -> 9 / 12
coverage-preserving queue    -> 10 / 12
consensus refine             -> 8 / 12
```

更重要的是数字背后的架构判断：当任务需要覆盖率、证据和人工审核时，最好的系统形态往往不是“给我最终答案”，而是“给我一条可审计、可修改、可继续推进的路径”。

这就是组合-集成之美。

## 思考题

如果把这个案例换成合同条款审查、医疗指南抽取、企业安全策略检查，你觉得 `coverage_preserving_union_queue` 还会是最优吗？什么时候你会放弃高召回队列，直接追求 compact final checklist？

## 参考

* Anthropic, *Building Effective Agents*，2024-12-19。
* OpenAI Agents SDK Tracing / Trace Grading 文档。
* LangGraph Durable Execution / Human-in-the-loop 文档。
