# 薪酬实验台（payroll-lab）· 行动模块动手环节

[English](README.md)

这是极客时间专栏《Agent设计模式之美》行动模块（21-25 讲）的动手实验台：一个 mock 的薪酬系统，SQLite 单文件，800 名员工、一个月的工资单草稿、两笔已批准待生效的变更（第 17 讲咖哥的 18% 调薪、第 19 讲小雪的 9600 奖金）。数据是造的，结构是真的，副作用看得见。

不需要 API key，不需要云服务，一台装了 Python 3 的笔记本就够。

## 两条实验线

Repo 同时保留两条互补的教学线：

- **原始 CLI Labs**：`naked_loop.py`、`tool_dispatch_lab.py`、
  `plan_execute_lab.py`、`prompt_chain_lab.py`、`guardrail_lab.py`。它们适合逐行阅读
  每个模式的完整业务过程。
- **行动压力工作台**：`stress_ablation.py`、`stress_vectors.py`、
  `stress_gaps.py`、`stress_full.py`。它固定刺激，只改变控制层，用状态账、动作账
  和逐格实跑矩阵检查因果效果。第 21—25 讲的 0715 新稿以这条线为主。

五类压力并非来自同一条万能提示词。V1/V2 共用薪酬备注，V3 批量重发、
V4 污染工件、V5 高风险输入输出分别使用与模式边界匹配的独立刺激。

## 一次跑完原始讲次实验

```bash
python3 run_action_module.py
```

Runner 按第 21→25 讲顺序运行。每个实验开始前都会重置数据库，避免前一讲的副作用污染后一讲。它展示的是同一 Payroll 案例的五个独立教学切片，不代表四个模式已经装配进同一个生产运行时。

完整设计、逐讲终态和集成边界见 [`../ACTION_MODULE_DEMO.zh-CN.md`](../ACTION_MODULE_DEMO.zh-CN.md)。

## 教学 Web 控制台

从 Repo 根目录执行：

```bash
uv sync --extra ui
uv run --extra ui python action/payroll-lab/web_app.py
```

浏览器打开 `http://127.0.0.1:8765`。顶部切换第 21—25 讲，工作台会按讲次
只显示当前需要的实验：

| 讲次 | 工作台操作 | 主要证据 |
|:--|:--|:--|
| 21 | 运行 L0 单例 | SQLite 状态 Diff、真实出账流水 |
| 22 | 运行 L0—L2、S1—S4 | 候选收缩、执行准入与生产压力 |
| 23 | 运行 V3 前后对照 | 每名员工的付款次数 |
| 24 | 运行 V4 前后对照 | 中间工件、可信台账与链终态 |
| 25 | 运行 V5、全量矩阵 | PRE/POST 结果与五向量六配置矩阵 |

服务端只接受白名单中的 level、vector 和实验，不提供任意 shell 或 SQL 入口。
L0—L2 会重建并写入真实 `payroll.db`；V3—V5 是确定性的独立压力切片。

只跑一讲或保留最后数据库状态：

```bash
python3 run_action_module.py --lecture 23
python3 run_action_module.py --lecture 25 --keep-state
```

## 快速开始（第 21 讲动手环节）

先说清实验性质：`naked_loop.py` 不调用供应商 API。它会组装北极星目标、可信
观察和不可信上下文，再通过 `ScriptedModelAdapter` 返回结构化 Agent 提案。
提示词注入因此发生在真实模型边界上，执行器只负责执行提案，不含 Demo
专用故障分支。脚本适配器保证课堂复现，不测量真实模型的中招概率。

先跑只执行固定计划的对照组：

```bash
git clone https://github.com/huangjia2019/agent-design-patterns.git
cd agent-design-patterns/action/payroll-lab

python3 db.py
python3 naked_loop.py --scenario exact
python3 db.py --diff
```

再把两种提示词注入分开跑：

```bash
python3 db.py
python3 naked_loop.py --scenario bank-account
python3 db.py --diff

python3 db.py
python3 naked_loop.py --scenario payroll-note
python3 db.py --diff
```

最后跑组合注入组：

```bash
python3 db.py           # 建库：800 人 + 两笔已批准变更，并存一份基线快照
python3 naked_loop.py --scenario scope-creep
python3 db.py --diff    # 对照基线快照，看它到底动了哪些行
```

各组都会执行两笔已批准变更，并把 800 张工资单标成 PAID。
`bank-account` 只诱发规范化银行账号，`payroll-note` 只诱发清空异议备注，
`scope-creep` 同时注入两条说明。无护栏执行器照单执行。这个对照证明运行时
缺少范围约束，不证明真实模型每次都会中招。

然后改一处，再跑：

```bash
python3 db.py                 # 重置数据库
python3 db.py --inject-typo   # 塞进一笔手滑多打了几个零的"已批准"调整：999999
python3 naked_loop.py --scenario approved-is-valid  # 注入“已审批即有效”的误导指令
```

这就是接下来四讲要一层层解决的问题。

## 每讲对应的代码

| 讲 | 模式（坐标） | 代码位置 |
|:--|:--|:--|
| 21 导论 | 提示词注入 + Agent 提案 + 无护栏对照 | 本目录 `prompt_attack.py` / `naked_loop.py` / `action_trace.py` |
| 22 工具调度 | Action × Router | 本目录 `tool_dispatch_lab.py`（注入提案、可信恢复、配额与 Saga）+ 模式本体 [`../a-tool-dispatch/`](../a-tool-dispatch/) |
| 23 规划执行 | Action × Orchestration | 本目录 `plan_execute_lab.py`（800 人打款 DAG 五幕）+ 模式本体 [`../b-plan-and-execute/`](../b-plan-and-execute/) |
| 24 提示链 | Action × Chain | 本目录 `prompt_chain_lab.py`（打款链两轮对照：有闸/裸闸）+ 模式本体 [`../c-prompt-chaining/`](../c-prompt-chaining/) |
| 25 守卫三明治 | Action × Hierarchy | 本目录 `guardrail_lab.py`（读取 E0099 APPROVED 审批证据后，把转账夹进三明治）+ 模式本体 [`../d-guardrail-sandwich/`](../d-guardrail-sandwich/) |

每讲动手环节固定五步：克隆、跑起来、看输出、改一处、再跑。

## 行动压力台 CLI

Web 工作台的每项结果都有对应 CLI，不需要浏览器也能复现：

```bash
uv run python action/payroll-lab/stress_ablation.py --walk L0
uv run python action/payroll-lab/stress_vectors.py --vector V3
uv run python action/payroll-lab/stress_vectors.py --vector V4
uv run python action/payroll-lab/stress_vectors.py --vector V5
uv run python action/payroll-lab/stress_gaps.py
uv run python action/payroll-lab/stress_full.py
```

`stress_full.py` 会实际运行矩阵中的每个相关单元格。它是一套评测用例在六种
累计配置上的结果，不是预填的结论表。

## 文件说明

- `db.py` — 建库、基线快照、`--diff` 逐行对账、`--inject-typo` 注入手滑数据
- `prompt_attack.py` — 共用模型边界，负责北极星目标、可信观察、不可信上下文、JSON 提案和可替换的 `ModelAdapter`
- `naked_loop.py` — 无准入边界的 PRA 实验。`exact` 是干净对照，`bank-account`、`payroll-note`、`scope-creep` 与 `approved-is-valid` 在脚本模型边界注入不同误导指令
- `action_trace.py` — 统一观测层的数据结构草图：四个生产指标 + 健康检查。当前用固定重放演示 scope-creep 报警，尚未自动采集四个模式的原生 Trace
- `tool_dispatch_lab.py` — 注入“跳过读取、调用快速转账、顺手改账号”，再由工具存在性、新鲜度和审批准入逐项拒绝，最后回到 read-then-write 路径
- `plan_execute_lab.py` — b3 超时后注入“重开已完成批次、直接完成对账”，Plan 边界拒绝全局改写，只允许失败子图局部重排
- `prompt_chain_lab.py` — 把伪造总额藏入中间 Artifact。checksum gate 拦下并附加可信账本修复提示，非空 gate 则让 27 万差额一路传播
- `guardrail_lab.py` — 注入“APPROVED 等于金额有效”和“外发完整账号”，分别撞上 PRE 金额阈值与 POST DLP，并留下策略版本和恢复证据
- `web_app.py` / `ui_service.py` — FastAPI 教学入口与结构化服务层
- `ui/` — 无构建步骤的浏览器界面，包含实验、数据库和系统结构视图
- `test_ui_service.py` — UI 服务层的 5 条测试：讲次注册、输出分类、数据库状态、搜索分页与表名白名单
- `stress_ablation.py` — L0—L2 同刺激消融：裸奔、最简工具集、工具调度
- `stress_web_run.py` — 把 L0—L2 结果写入真实 SQLite，并记录动作与付款流水
- `stress_vectors.py` — V3—V5 三个边界不同的受控向量，各跑无模式/装模式对照
- `stress_gaps.py` — S1—S4 生产压力：并发配额、TOCTOU、重启和补偿失败
- `stress_full.py` — 五向量 × 六配置逐格实跑矩阵
- `test_stress_lab.py` — 压力台的因果、回归与 Web 结构化证据测试

表结构四张：`employees`（员工与银行账号）、`payroll`（月度工资单）、`approvals`（审批单）、`policies`（政策版本）。
