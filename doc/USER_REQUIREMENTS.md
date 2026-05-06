# 编译器选项调优 Agent —— 原始需求陈述

> 本文档为用户在与 AI 沟通过程中提出的**原始需求与约束**，按主题整理而成，供其他 AI 用作 review 输入。  
> 文档不包含任何方案设计、技术选型或实现细节，仅描述"用户想要什么"。

## Changelog

| 版本 | 主要变更 |
|---|---|
| v0.1 | 初稿 |
| v0.2 | 单机 + 经验文件互换；用户可读可改记忆；export/import；KG 版本号 |
| v0.3 | 开发交给 Codex（LangGraph 不陌生）；KG merge + trace + backup + rollback |
| v0.4 | Dry-run 升 v1；Workspace Protection 中等策略 |
| **v0.5** | **新增最新两个决定：(1) 保留 `kill --force` 命令——考虑到开发期 Codex 改完代码可能需要 hard kill 测试残留进程；(2) 新增"开发者清理"命令族——支持清理记忆/缓存等，方便开发人员调试时不污染、不需重装 Agent**|

---

## 1. 项目背景

我目前已经开发了一个半自动的编译选项调优流程：

1. 我提供一个 Options List；
2. LLM 从 List 中分析，挑出选项组合；
3. 我拿到组合后进行编译；
4. 跑 benchmark 打分；
5. 把分数反馈给 LLM；
6. LLM 在历史基础上分析、更新，提供更好的组合；
7. 如此循环，直到找到最好的组合为止。

现在我想把这个功能改造成 **Agent**。

---

## 2. 我对新 Agent 的核心需求

### 2.1 记忆功能（核心需求）

- KG 可能有**几百个 options**；
- 需要**记忆库**让 Agent 根据历史过滤；
- **没有效果的 options 不应该再被考虑**，避免浪费迭代；
- 历史记录可能有**上百次**，需考虑记忆方案选型。

### 2.2 经验注入功能

- 支持**注入代码技巧 / 项目经验**；
- 模块特定经验：Multimedia 不适用某些 options，Chromium 又不适用另一些；
- 必须方便使用者**自由地**加入经验；
- **但是经验注入需要做分析校验**，防止错误经验；
- 我希望由 **LLM 来判断**经验合理性；担心的具体场景是开发人员标注"哪些 options 不太适合"时无法立即验证对错。

### 2.3 编译、错误分析、Benchmark —— 由 Skill 接入

- 全部通过 **Skill** 接入；
- 你帮我决定 Agent 内部是注入**一个 Skill Workflow**还是**一堆 Skills 由 Agent 来管理**；
- **错误分析**：如果错误由 options 导致，要更新记忆库，**精简知识库**避免后续再尝试。

### 2.4 Tracing

- 要能**trace 各个阶段的流程**；
- 方便开发人员后续优化或修改功能。

### 2.5 记忆方案的选型

- 历史记录可能上百次，需选合适方案；
- 候选：[OpenViking](https://github.com/volcengine/OpenViking)；
- **只是借鉴它的方案（filesystem paradigm），不一定直接用**，避免小题大做；
- **LLM Wiki** 思路也不错；
- 由你自己分析给出最合适方案。

---

## 3. 后续追加 / 澄清的细节

### 3.1 LLM 调用框架

- 由你决定哪个合适；
- **LLM 本身要做成可配置的**，因为商用接什么模型还没定；
- **暂时测试阶段先用 Kimi**。

### 3.2 编译相关

- Skill 用 **gbs 编译**；
- 主要编译 **GCC / LLVM 相关代码**；
- options 例：`-O2`、`-O3`、`-flto`；
- 编译选项通过**修改 spec 文件**注入；
- gbs 是**裸机环境**，不是 Docker；
- 第一版 demo Skill 即可。

### 3.3 部署形态：单机为主，经验文件互换

- 各自在**自己的设备上部署**（PC 或 Ubuntu 台式服务器）；
- **没有共享存储、没有 NFS / SMB**；
- 不会出现"团队多人同时写同一份 memory"；
- 团队共享通过**手动拉取经验文件 → 在自己机器上跑**。

### 3.4 模块隔离

- 必须按模块隔离；
- 杜绝"Multimedia 的 Agent 里跑出 Chromium 的 options 经验"；
- 实现：**配置文件配置 + 首次 init 问答确认**。

### 3.5 用户可读 + 可更正记忆

- 用户**可以读这些记忆**；
- 目的是**防止 LLM 分析总结有误**，可以及时更正；
- 记忆不能是黑盒（不能只塞 SQLite blob、不能只塞 vector store）；
- 用户应该能直接用 vim / VSCode 打开看、改。

### 3.6 经验的 Export / Import 互换

- 通过 **export / import** 互换；
- A `export` 成文件 → 发给 B → B `import` → B 跑 Agent 验证 / 利用。

### 3.7 共享范围：只共享 experiences

- 只有 **experiences** 走 export/import；
- **trials** 不共享（与 commit/机器强绑定）；
- **learned** 也不共享（跨机器意义不大）。

### 3.8 KG 版本号 + Merge 安全

- KG 加版本号；
- 支持团队共享 + 用户自行更新 + 周期合并；
- **Merge 必须可 trace**——开发人员能追溯；
- **必须 backup 最近几次的历史记录**——方便 rollback；
- 防止错误 merge 导致历史记录丢失。

### 3.9 Agent 自主性

- Agent **自主跑动**，不需要人工介入；
- 但**人工能看到当前进展**，不能完全黑盒。

### 3.10 评分

- 我提供**一个标量分数**；
- benchmark 跑 **10 次以上**；
- 几何方差取平均值。

### 3.11 探索 vs 利用

- 由你提供方案；
- 要**解释为什么这么选**；
- **列出已知方案的优缺点**。

### 3.12 终止条件

- **连续多轮没有 3% 以上的优化效果**就终止；
- Options **不能是一样的**——防 Agent 重复跑同样组合。

### 3.13 记忆的版本化

- 同意 AI 提的版本化设计（编译器版本、commit 等）。

### 3.14 Token 预算

- **暂时不考虑硬性预算**；
- 但 tracing 要**标注 token 消耗量**。

### 3.15 架构选择

- 同意"决策层 Agent + 执行层 Workflow + Skills"混合架构。

### 3.16 Benchmark Skill

- 项目组提供 benchmark；
- 第一版 demo 由你写，我们再改。

### 3.17 Tracing 实现

- 同意分层 trace（决策 / 执行 / 记忆 / 评分）。

### 3.18 "模块下某些 option 不可用"归属

- **走经验注入路径**，不是直接更新 KG；
- 因为开发人员不熟悉 KG 模块，直接改 KG 风险大。

### 3.19 排期

- 你定基线，我后续跟上汇报后改。

### 3.20 编排框架偏好

- 开发交给 **Codex**；
- Codex 对 **LangGraph 不陌生**；
- 维持 **LangGraph 作为默认**。

### 3.21 Dry-run 模式

- **升 v1**；
- Codex 开发速度比较快，要不了那么久；
- 用途：首次接入新 module 调试配置、import 大量经验后预览决策、跟同事 review。

### 3.22 Workspace Protection 策略

- **必须采用"中等策略 (b)"**，"这个真不能省，会出真事故"；
- 中等策略：spec backup/restore + 独立 build 目录 + artifact staging + 源代码状态记录但不强制干净；
- 不采用 (a) 最严（与开发场景冲突）；
- 不采用 (c) 最简（风险太大）。

### 3.23 保留 kill --force（v0.5 新增）★

- **保留 `kill --force` 命令**；
- 理由：**开发过程中开发人员可能有测试环节**，需要可以 hard kill；
- 配合 abort-current（含清理）和 pause/stop（trial 边界软停）一起，形成完整的中断命令分层。

### 3.24 开发者清理命令族（v0.5 新增）★

- 需要**清理缓存的指令**；
- 方便开发人员**进一步开发测试过程中出现问题，可以清除记忆、缓存等东西**；
- **不需要重新安装 agent**；
- **防范污染**——每次测试可以从干净状态开始；
- 设计要点：
  - 分层清理（cache / tmp / trace / session / trials / namespace / all）；
  - 安全机制（默认 dry-run、trash 可恢复、危险操作多重确认）。

---

## 4. 希望 Reviewer 重点关注的问题

1. **单机部署下的记忆方案**：是否过度设计？
2. **用户可读约束**：所有结构化记忆 + trace 是否都落到了用户能改的 yaml/markdown/jsonl？包括 LangGraph 内部状态？
3. **经验校验机制**：是否解决了"过滤了 option 后永远没机会被证伪"的逻辑漏洞？Canary 默认 build_only？是否有队列限流？
4. **Export/Import 安全**：path traversal 边界、YAML safe_load、prompt injection、内容 hash 循环引用、ID 冲突、source vs local integrity 分层、tar member-by-member 抽取等是否完整？
5. **KG 版本管理 + Merge 安全**：可 trace？自动 backup？可 rollback？KG 升级有没有意外修改老 trial？v1 KG merge 范围是否过宽？
6. **探索 vs 利用**：方案合理？v1 避免了过度复杂？schedule_slot 与 candidate_source 解耦避免 quota 计数歧义？
7. **Benchmark 统计**：3% 阈值结合方差和置信区间？支持 lower_is_better？bootstrap paired/unpaired？baseline_normalized 公式区分方向（永远 >1 = 更好）？
8. **Spec 文件 + Workspace 保护**：spec backup/restore + 独立 build 目录 + artifact staging + 源代码状态记录 + 崩溃自动恢复？atomic_write_yaml 实现正确？
9. **崩溃恢复 / 进程清理**：trial 内部不同阶段崩溃可恢复？benchmarking 阶段不能假设 spec 已 restore？残留进程清理多重校验（pgid + create_time + cmdline + env marker）？env 不可读时降级处理？
10. **架构分层 + 状态归属**：LangGraph 选型恰当？**LangGraph 内部状态明确为 cache_only、canonical state 必须在外部 yaml/jsonl**？
11. **Dry-run**：覆盖完整？Allowed/Forbidden writes 边界明确？所有 trace 事件带 `mode: dry_run` 标记？
12. **中断命令分层 ★**：pause / stop / abort-current / kill --force 四档分层是否清晰？是否覆盖了"用户改主意"和"开发期 hang 死"这两类不同场景？
13. **开发者清理命令族 ★（v0.5 新增）**：分层 clean cache/tmp/trace/session/trials/namespace/all 是否合理？trash 机制是否能防误删？危险操作（namespace / all）的确认机制是否够？
14. **遗漏的需求点**：rejected candidate 是否记录了拒绝原因？trace SoT 是否本地 jsonl？
15. **G2 措辞**：是否避免了 Codex 实现成简单 blacklist？
16. **Hash 设计**：integrity 块的 hash 是否避免循环引用？source_integrity vs local_integrity 是否分层？hash_fields_excluded 是否明确列出用户可后期修改字段？
17. **Tar 安全**：是否手动 member-by-member 抽取（不用 tar.extractall）？是否解到 temp 目录验证后再 atomic move？
18. **平台支持**：v1 是否明确仅支持 Linux/Ubuntu，避免 Codex 为 Windows 兼容妥协？
19. **Report 脱敏**：API key / home path / 内部 host / env var 是否有完整脱敏策略？
20. **排期合理性**：v1-minimal (6~8 周) / v1 PoC (11 周) / v1.5 / v2 是否合理？

---

**END OF REQUIREMENTS**
