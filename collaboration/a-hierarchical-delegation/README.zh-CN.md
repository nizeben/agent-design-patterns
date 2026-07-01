# a · 层级委派 Hierarchical Delegation

> 专栏第 **07-02** 讲 · 模式 · 协作 × 层级
>
> [English README](README.md)

## 问题

一个薪酬 SaaS Agent 跑 6 月结算：**800 名员工**，十几个 client，好几套薪资口径。
一个 Agent 在单一上下文里算完 800 人，又慢，中间任何一个人算错就得满盘重来。自然的
办法是组一支团队：一个**结算主管**把花名册按 client 拆批，每批交给一个**工人**。

第一版做了委派，前三批又快又干净。到第四批，主管开始胡言乱语，输出结构全乱了。工人
没错，是主管被淹了：为了汇总，它把每个工人**干活的全过程**都读了进来，到第四批时，
六成上下文都是别的 Agent 的原始计算，真正要它判断的东西反而被挤没了。

根因：主管累积的是工人的**过程**，不是工人的**结果**。委派不是「把活分出去」，是
「分出去还不被工人的过程淹死，也不盲信工人交回来的东西」。

重写之后：工人在隔离上下文里跑、只回一个 schema 化的 `SalaryBatchArtifact`；主管只读
artifact、绝不读原始过程，每份产出都过一道确定性闸门。

## 模式

两个命名工具（来自讲稿）：

**委派三件套** —— 派任何一批之前，先钉住三样：

- **任务规约 Spec** —— 工人的目标、输出格式、工具白名单、以及*边界*（哪些不归它管，
  这是防批次重叠的第一道防线）。
- **上下文预算 Budget** —— 工人从空白上下文起跑，只回一个 artifact，原始计算永不进
  主管。
- **验收闸门 Gate** —— 一道确定性 `SafetyBoundary`（金额/置信度/待复核/verdict）判放行
  还是转人工。编在程序里，绝不交给提示词。

**主管不下场** —— 三条能写成 assert 的红线：主管只看 artifact 不看过程、工人之间不
横向直连（hub-and-spoke）、主管只做拆/派/合/验、不亲自算一分钱。

## 两套可运行实现

同一个模式、同一个 `pattern.py` 闸门，两种编排哲学：

| | [`langgraph/`](langgraph/tutorial.ipynb) | [`claude-agent-sdk/`](claude-agent-sdk/tutorial.ipynb) |
|---|---|---|
| **你写什么** | 显式 `StateGraph`：decompose 节点 + `Send` 扇出 + reducer 扇入 + 主管闸门，每条边看得见 | 声明式 `AgentDefinition`，运行时按 `description` 委派、自动隔离上下文 |
| **隔离** | 你自己控（`output_mode="last_message"` / 只回 artifact） | 内建 —— 每个子代理 fresh context，只回 final message |
| **模型** | provider 无关（`model_config`，默认 `ernie-5.1`） | Claude 原生（主管 `opus`、工人 `haiku`） |
| **规模** | `Send` + reducer | 少量批用子代理；几十上百批用 `Workflow` 工具 |

这个分野对齐 repo 里的 Guardrail Sandwich（显式图 vs 隐式 middleware）：LangGraph 版把
隔离与并行做成**显式**工程，Claude Agent SDK 版把它们做成**原生**能力。

## 文件

| 文件 | 内容 |
|---|---|
| [`pattern.py`](pattern.py) | 框架无关参照（约 130 行）：`WorkerSpec`、`SalaryBatchArtifact`、`SafetyBoundary`、`SettlementSupervisor`。可插拔的 `dispatch` 是两套 tutorial 各自填的接缝。 |
| [`example.py`](example.py) | 用 mock 工人跑 800 人委派，无需 API key。 |
| [`test_pattern.py`](test_pattern.py) | 9 个测试：拆批/边界、四个闸门触发、工人失败隔离、并行派发。 |
| [`langgraph/tutorial.ipynb`](langgraph/tutorial.ipynb) | 一步步：State + reducer → worker 节点 → `Send` 扇出 → 主管闸门。 |
| [`claude-agent-sdk/tutorial.ipynb`](claude-agent-sdk/tutorial.ipynb) | 一步步：`AgentDefinition` 工人 → `ClaudeAgentOptions` → `query()` 委派 → Python 闸门。 |

## 运行

```bash
# 框架无关的核心 —— 无需 API key
python collaboration/a-hierarchical-delegation/example.py
pytest collaboration/a-hierarchical-delegation/test_pattern.py -v

# 两套实现需要模型 —— 见 .env.example
```

## 它在双轴里的位置

协作（认知功能）× 层级（执行拓扑）。协作模块里的邻居：扇出聚合（同一批、不同视角）、
对抗评审（第二个 Agent 只挑错）、交接链（一根接力棒沿流水线传）。见
[双轴矩阵](../../README.zh-CN.md)。
