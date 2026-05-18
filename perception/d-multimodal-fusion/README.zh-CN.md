# d · 多模态融合（Multi-Modal Fusion）

> 专栏第 **02-05** 讲 · 模式 · 感知行 × 并行列
>
> [English README](README.md)

## 解决的问题

Agent 接到一份 80 页 PDF 研报。要输出三件事——核心论点摘要、所有数字结论的事实
核查、给客户经理的销售要点。工程师试了两条自然路径，都翻了。

* **All-in-one。** 整份 PDF 喂给 Claude 的 PDF API。~90K token，Sonnet 4.6 输入
  单价折下来 $0.27/次。摘要还行，**数字核查崩了**——agent 把 47 页 Y 轴
  "市场规模 RMB 5800 亿"读成"5800 万"，差三个零。Y 轴刻度的空间信息在
  PDF 栅格化 token 里没看清。
* **All-text。** OCR 整本，丢掉图，纯文本喂。~35K token。数字读对了，**所有
  图表的空间信号全没了**——摘要变机械、销售要点空洞。客户经理看了直接退回。

三周的 prompt engineering 都救不了。问题不在 prompt——**数据的形态不适合
模型消化**。

## 模式本体

每种输入模态路由到**最便宜但又够用的形态**，再合并：

| 模态 | 怎么处理 | 为什么 |
|---|---|---|
| **TEXT** | 直接透传 | 已经是最便宜的形态 |
| **IMAGE** | 空间信息是信号时保留为图（图表、示意图、含 UI 文本的截图）；不是时 OCR 后丢图 | 市场规模图的 Y 轴是信号；公司 logo 不是 |
| **TABLE** | 转 markdown | 比栅格化省 80% token，结构信息保留 |
| **PDF** | TOC + 关键页 + 关键图表 | 80 页 → ~3 页紧凑表示，20K 代替 90K token |
| **LOG** | bash 预过滤 → sub-agent 抽取 → 紧凑摘要 | 三段式，因为生产日志 95% 是噪声 |
| **AUDIO** | STT 转文本，再走文本路径 | 模型听不见波形 |
| **SQL_RESULT** | markdown table + top-N 抽样 | 超过 N 的行通常不加信号 |

每条输入打一个 `FusionEvent`（modality / tokens_out / method / 毫秒数）。
`health_check()` 标红 signal——image token 占比 > 50%、log token 占比 > 40%
（说明 bash 预过滤没起作用）。

模式的核心主张：**数据形态对了，token 预算少一个数量级，答案质量同时上去**。
这两件事不是 trade-off。

## 快速跑通

```bash
python perception/d-multimodal-fusion/example.py
pytest perception/d-multimodal-fusion/
```

Demo 跑研报场景。无融合 ~90K token，融合后 ~1.7K token（合成 demo 上 98%
削减，真实生产数据大约 80%）。

```
v3 multi-modal fusion : 1,724 tokens (5 content blocks)
v1 all-in-one (naive) : 89,693 tokens
Savings               : 87,969 tokens (98% reduction)
```

## 文件清单

| 文件 | 说明 |
|---|---|
| `pattern.py` | `MultiModalFuser` + 8 `ModalityType` + `ModalityInput` + `FusionEvent` + `FusionResult`，约 220 行 |
| `example.py` | 80 页 PDF + 图表 + 100 行供应商表格 + 60 行噪声日志 + 用户文本 |
| `test_pattern.py` | 10 条不变量：各模态路由、PDF 抽取、bash+subagent 日志流水线、SQL 紧凑、health check、keep_as_image 覆盖 |

## 工程引用（已核对）

* [Anthropic Vision API 文档](https://platform.claude.com/docs/en/build-with-claude/vision) —— token 数学：`width × height / 750`，单图上限 1568 token
* [Claude PDF support](https://docs.claude.com/en/docs/build-with-claude/pdf-support) —— 30 页文本密集型 PDF ≈ 56-60K token 原生
* [Anthropic Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) —— 最小高信号 token 集合的提法
* [Manus Context Engineering 博客](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) —— 100:1 输入输出比，正是激进 shape 数据的动机
* LLM 做日志结构化：arXiv:2511.18727（LogSyn）+ arXiv:2510.24031（LLMLogAnalyzer）

## 什么时候不该用这个模式

* **输入很小。** 200 行配置文件、5 行 API 响应——不用融合，直接喂。
* **预处理代价超过省下的 token。** OCR 两页省 800 token 不值你 4 秒延迟。
* **模型自带的多模态比你的 pipeline 还便宜。** Anthropic、OpenAI、Google 都在
  滚动发布直接 PDF / 直接图像支持。每季度重新核对一次价目，这个模式的部分价值
  会逐渐被模型本身吸收。
