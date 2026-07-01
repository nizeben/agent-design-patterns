# c · 对抗评审 Adversarial Review

> 专栏第 **07-04** 讲 · 模式 · 协作 × 循环
>
> [English README](README.md)

## 问题

一个 AI 出行助手排好了行程，20:00 的航班、一家酒店、一辆去机场的滴滴，正要下单扣钱。
每一项单看都对，机票是真的、酒店有房、车也叫到了。可拼在一起看，滴滴的预计到达是
19:40，登机口 19:30 就关。这份行程会让你眼睁睁看着飞机飞走。

排这份行程的 Agent 自己发现不了。它刚办成三件事，正处在「我干得不错」的状态里，你让它
自己审一遍，它大概率说「没问题，下单」。这不是它笨，是生成者和评审者是同一个，同上下文、
同一套自我评价，它没有动力去否定自己刚做出来的东西。

所以对抗评审加一个 Agent，只干一件事，攻击这份行程。难的不是加评审，是保证这个评审真的
**独立**，而不是和作者一起装样子的橡皮图章。

## 模式

两个命名工具（来自讲稿）。

**独立性三隔离** —— 一个评审者算不算独立，看三样东西有没有和作者隔开。

- **上下文** —— 只看成品行程，看不到作者是怎么一步步说服自己的。
- **目标** —— 任务是「找出所有会失败的地方」，不是「判断能不能用」。措辞决定它是挑刺
  还是和稀泥。
- **身份** —— 是另一个 Agent，最好连模型都换一个。自己评自己，提示词再严厉，也还是同一
  套权重在打分。

**只提异议不背书** —— 评审者只交一张异议清单，交不回来一句「挺好的」。放行由确定性的
`ReviewGate` 算（阻断级异议为零），不由评审者说了算。一个能说「通过」的评审者，早晚会为了
显得配合而通过。

橡皮图章比没有评审更坏，它制造虚假信心。所以 `pattern.py` 遇到不独立的评审者会直接拒绝
这场评审。

## 两套可运行实现

同一个模式、同一道 `pattern.py` 闸门，两种把循环连起来的方式。

| | [`langgraph/`](langgraph/tutorial.ipynb) | [`claude-agent-sdk/`](claude-agent-sdk/tutorial.ipynb) |
|---|---|---|
| **循环** | 一条显式回边 `revise → review`，在 LangGraph Studio 里看得见 | 一个 Python `for` 循环，每轮重新 spawn 评审子代理 |
| **独立性** | 你控，评审节点只读成品行程 | 内建，评审子代理全新对话、自己的 model |
| **放行** | `route` 复用 `ReviewGate` | Python 复用同一个 `ReviewGate` |
| **模型** | provider 无关（`model_config`）| Claude 原生（`sonnet` 评审，和排行程的分开）|

两边的闸门是同一个。模型负责挑错，放不放行由闸门说了算，不由模型。

## 文件

| 文件 | 内容 |
|---|---|
| [`pattern.py`](pattern.py) | 框架无关参照（约 150 行）：`Itinerary`、`Objection`、`IndependenceGuard`、`ReviewGate`、`AdversarialReview` 循环。可插拔的 `Reviewer` 是两套 tutorial 各自填的接缝。 |
| [`example.py`](example.py) | 用 mock 评审者跑出行程审查，无需 API key。第一轮逮住滴滴 blocker，第二轮放行。 |
| [`test_pattern.py`](test_pattern.py) | 9 个测试：独立性拒绝、闸门严重度规则、收敛/修改/升级、带阻断级绝不自动放行的不变量。 |
| [`langgraph/tutorial.ipynb`](langgraph/tutorial.ipynb) | 一步步：State + 转数计数 → 评审节点 → `route` + `revise` → 回边循环。 |
| [`claude-agent-sdk/tutorial.ipynb`](claude-agent-sdk/tutorial.ipynb) | 一步步：独立评审 `AgentDefinition` → `query()` 循环 → Python 闸门。 |

## 运行

```bash
# 框架无关的核心 —— 无需 API key
python collaboration/c-adversarial-review/example.py
pytest collaboration/c-adversarial-review/test_pattern.py -v

# 两套实现需要模型 —— 见 .env.example
```

## 它在双轴里的位置

协作（认知功能）× 循环（执行拓扑）。最近的邻居是反思模块的生成批评，那是一个 Agent 自己
评自己，这一讲是专门请一个独立的 Agent 来攻击。同模块的邻居：层级委派、扇出聚合（都是
合作的 Agent），交接链（一根接力棒沿流水线传）。见 [双轴矩阵](../../README.zh-CN.md)。
