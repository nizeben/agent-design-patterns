# c · 渐进发现（Progressive Discovery）

> 专栏第 **02-04** 讲 · 模式 · 感知行 × 循环列
>
> [English README](README.md)

## 解决的问题

你不知道哪些文件相关。Bug 报告说"订单确认邮件偶尔显示其他客户的订单"。Codebase
是 15000 文件的遗留 monolith，原作者跑了一半，没有文档告诉你订单邮件 pipeline
走哪些文件。

三种不工作的思路：

* **全 codebase 喂给 agent**。再小的 monolith 折下来都是 ~800K token，远超窗口。
  切片并行喂，每片 agent 都说"这片没看到 bug" — 因为没人看到全局。
* **RAG**。整体 embedding + 语义检索。但出问题的文件用 `merge_user_state` 这种
  变量名，注释里没"order"也没"email"，语义召回根本对不上。
* **按拓扑序逐个读**。听起来严谨，实操变成 15000 次 read，没收敛点。

你需要的是一个资深工程师在陌生 codebase 里实际的导航方式 — grep、读几个、
follow call chain。

## 模式本体

三阶段在一个有界循环里：

| 阶段 | 做什么 | 典型量级 |
|---|---|---|
| **FORAGE** | 广扫，grep / glob 找 ~30 候选 | 秒级，几百路径 |
| **FOCUS** | 挑 top 5-8 个完整读 | 秒级，~5K token |
| **DEEPEN** | 追 imports / 调用链 / 引用 | 秒级，~3K token |

找到信号就退出，没找到就用读到的内容 refine 关键词进下一轮。单循环 token 预算
+ max-cycles 上限双重约束。每个阶段都打 trace 事件，事后能查漂移。

**不变量：永不预先 embedding 整个 codebase**。发现是按需的、结构感知的、有界的。
完整循环典型代价 ~18K token，跟仓库总大小**无关**。

## 快速跑通

```bash
python perception/c-progressive-discovery/example.py
pytest perception/c-progressive-discovery/
```

Demo 造了一个 200 文件的合成 Rails monolith，两个 bug 相关文件埋在噪声里。给到
合适的初始关键词后，discoverer 1 轮 530 token 就定位到 bug。

```
Codebase: 200 files
Task    : find why order confirmation emails sometimes show another customer's order
Cycles run     : 1
Total tokens   : 529
Final files    : 5
  · app/mailers/order_confirmed.rb ← bug 源 1（邮件器）
  · app/services/order_history_emailer.rb       （干扰项）
  · ... (再 3 个)
  · cache/user_state                  ← bug 源 2（缓存键）
Bug located    : True
```

## 文件清单

| 文件 | 说明 |
|---|---|
| `pattern.py` | `ProgressiveDiscoverer` + `Phase` + `Candidate` + `DiscoverySession` + `DiscoveryEvent`，约 230 行 |
| `example.py` | 200 文件合成 Rails monolith + 真实形状的 bug |
| `test_pattern.py` | 8 条不变量：阶段顺序、预算执行、success-exit、max-cycles cap、deepen 跟 imports、health check |

## 工程引用（已核对）

* **Boris Cherny**（Claude Code 创始人）在 X 上[那段关于 Claude Code 弃 RAG 改走 agentic search](https://x.com/bcherny/status/2017824286489383315) 的原话：
  > "Early versions of Claude Code used RAG + a local vector db, but we
  > found pretty quickly that agentic search generally works better.
  > Internal benchmarks showed that agentic search outperformed RAG by
  > a lot, which was surprising."
* [Anthropic 的 Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)，提出"最小高信号 token 集"框架
* [Pirolli & Card 1999《Information Foraging》](https://psycnet.apa.org/record/1999-11644-001)（Psychological Review 106(4)）—— forage / focus / deepen 三段论的认知科学根源
* [Aider 的 `repomap.py`](https://github.com/Aider-AI/aider/blob/main/aider/repomap.py) —— 走另一条路（预建符号图），跟 agentic search 互补不对立
* [Augment Code Context Engine](https://www.augmentcode.com/context-engine) —— 持久索引派的参考实现（40 万文件 6 分钟索引，45 秒增量更新）

## 什么时候不该用这个模式

* **Agent 已经知道文件。** 单文件编辑、focused refactor、相关 scope 已经被预先
  限定 —— 跳过 forage 直接读。
* **数据不适合 grep。** 自然语言知识库、聊天记录、非结构化文档 —— RAG 才是
  合适的工具。两个模式互补不打架。
* **信号在 metadata 而不在代码。** git blame、commit history、CI logs ——
  那是另一组感知工具，不是 Progressive Discovery 的失败案例。
