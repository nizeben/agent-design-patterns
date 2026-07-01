# b · 扇出聚合 Fan-out-Gather

> 专栏第 **07-03** 讲 · 模式 · 协作 × 并行
>
> [English README](README.md)

## 问题

6 月结算做完了，工资条都算完，可总账一汇总差了一笔（比如 37 万），缺口从哪来不知道。
上一讲的层级委派解决不了这个。层级委派把 800 人拆成一批批，各算各的一片。这次是同一笔
总额，要让几个 Agent 用不同的口径各算一遍，看差在哪。

工程师一听「并行」就兴奋，很快写出把任务扇给十几个 worker 的代码，扇出那段又漂亮又快。
然后 gather 那段就一行 `concatenate`，把十几份结果拼起来交上去。结果是一份读不下去的
报告，同一个风险点被三个 worker 用三种措辞各标一遍，六百项里六成是重复，使用者翻两页
就放弃了。

这就是扇出聚合的真相，散开容易，收回难。fan-out 几乎不用设计，`asyncio` 一把梭。真正
决定这套东西有没有用的是 gather，怎么把 N 份有歧义、有重叠、可能互相矛盾的结果，合成
一个可信的答案。聚合器才是扇出聚合的灵魂。

## 模式

两个命名工具（来自讲稿）。

**聚合器四问（Aggregator's Four Questions）** —— 开 fan-out 之前先答，因为设计得从聚合器
倒着来，先想清楚结果怎么收，再决定活怎么散。

- **第一问，可相加还是互斥候选。** 每个 worker 各看一面、拼起来是全景，用综合；几个
  worker 对同一问题给不同答案，用投票或裁判。这一问定聚合策略族。
- **第二问，冲突怎么裁。** 多数投票、置信度加权、独立裁判 Agent、还是转人审。高风险场景
  裁决规则必须是确定性的。
- **第三问，重叠怎么去。** 要不要上去重管线，把「对赌条款增加」和「earnout 扩大」认成
  同一件事。六百项报告压到八十项就靠这一问。
- **第四问，接缝谁来看。** 有些问题只在 worker 切片的交界处才暴露，任何单个 worker 都
  看不到。要不要在 gather 之后加一个专看跨 worker 问题的评审 Agent。

**分歧定位三层（Divergence-to-Root-Cause）** —— 这一讲最关键的一次升级。让每个 worker
绑定一个可归因的边界（一个数据源），各算同一笔总额，它们之间的分歧就从噪声变成了定位
信号。

- **一致** —— 缺口不在这里，放过。
- **分歧可归因**（分项的值收敛成对立的两簇） —— 分歧的位置就是缺口的位置，直接指到源。
- **分歧不可归因**（不收敛） —— 退回人审。

前提就一句，让 worker 绑定不同的数据源。如果只是拿同一份数据反复采样，分歧就退化回
「只能报不确定」，定位不了任何东西。

## 两套可运行实现

同一个模式、同一个 `pattern.py` 聚合器，两种编排哲学。

| | [`langgraph/`](langgraph/tutorial.ipynb) | [`claude-agent-sdk/`](claude-agent-sdk/tutorial.ipynb) |
|---|---|---|
| **扇出** | 显式 `StateGraph`：`Send` 把同一份 rows 发给 N 个 source worker，reducer 把读数扇回来，每条边看得见 | 每个数据源一个 `AgentDefinition`，运行时经 Agent 工具委派，或每源一个 `query()` |
| **隔离** | 你自己控（只写一个 reduced key） | 内建 —— 每个子代理 fresh context，只回 final message |
| **聚合** | 一个 `gather` 节点调 `Reconciler` | 同一个 `Reconciler`，在 Python 里，子代理返回之后跑 |
| **模型** | provider 无关（`model_config`，默认 `ernie-5.1`） | Claude 原生（`sonnet` 编排、`haiku` 工人） |

两边的聚合是同一段代码，这正是把它留在 `pattern.py` 的原因。聚合逻辑框架无关，而且是
确定性的。模型负责把数据搬回来，缺口在哪不由模型投票。

## 文件

| 文件 | 内容 |
|---|---|
| [`pattern.py`](pattern.py) | 框架无关参照（约 150 行）：`FanOutGather`（并行派发 + 失败隔离 + `min_success_rate` 底线）与 `Reconciler`（三层聚合）。可插拔的 `FanoutFn` 是两套 tutorial 各自填的接缝。 |
| [`example.py`](example.py) | 用 mock 工人跑总账多口径核算，无需 API key。两笔缺口各自定位到子系统。 |
| [`test_pattern.py`](test_pattern.py) | 11 个测试：并行派发、失败隔离、成功率底线、三层分歧、additive 去重、接缝评审、端到端定位。 |
| [`langgraph/tutorial.ipynb`](langgraph/tutorial.ipynb) | 一步步：State + reducer → source worker → `Send` 扇出（同一份 rows）→ `gather` 节点。 |
| [`claude-agent-sdk/tutorial.ipynb`](claude-agent-sdk/tutorial.ipynb) | 一步步：每源一个 `AgentDefinition` → `ClaudeAgentOptions` → `query()` 扇出 → Python 聚合。 |

## 运行

```bash
# 框架无关的核心 —— 无需 API key
python collaboration/b-fan-out-gather/example.py
pytest collaboration/b-fan-out-gather/test_pattern.py -v

# 两套实现需要模型 —— 见 .env.example
```

## 它在双轴里的位置

协作（认知功能）× 并行（执行拓扑）。协作模块里的邻居：层级委派（同一支队伍、不同的
分片）、对抗评审（第二个 Agent 只挑错）、交接链（一根接力棒沿流水线传）。最容易混的是
推理模块的迭代假设验证（推理 × 循环），那是一个 Agent 顺着一条线往深挖，这一讲是多个
Agent 并行地各算一遍，信号来自它们之间的分歧。见 [双轴矩阵](../../README.zh-CN.md)。
