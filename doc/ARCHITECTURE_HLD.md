# CompilerGYMAgent — 系统架构设计文档 (HLD)

> **文档类型**：High-Level Design（架构层设计）
> **定位**：全系统架构真相源 —— 对齐已建成现状 + 后续待建设计，供治理、对齐、接手使用。
> **级别**：HLD。描述组件构成、组件交互、关键设计决策与不变量、数据流与契约；**不下到实现细节**（函数签名、算法伪代码留各 phase 的 SUMMARY / 代码）。
> **状态**：v1.3（基线，可落地）。08a 完成时建 v1.0 → 四份外部 AI review 修订为 v1.1 → 二轮 review 修订为 v1.2 → 7.0-contracts 冻结后 §4.1 更新为 v1.3。

## 文档体系定位

本项目有五类文档，职责不重叠：

| 文档 | 角色 | 何时读 |
|---|---|---|
| `doc/USER_REQUIREMENTS.md` | 用户原始意图（想要什么） | 确认需求来源 |
| `doc/REQUIREMENTS.md` | 详细需求规格（FR-* 功能需求） | 实现某 phase 前查具体需求 |
| **`doc/ARCHITECTURE_HLD.md`（本文档）** | **架构真相**（系统怎么构成、怎么协作、不变量） | **理解全局、对齐、接手** |
| `dev_memory/DECISIONS.md` | 决策日志（每个设计决策的论证与权衡，累积） | 追溯某决策"为什么这么定" |
| `dev_memory/ROADMAP.yaml/.md` | 进度真相（phase 顺序、状态、依赖、估算） | 看现在做到哪、下一步 |

**本文档不重复 DECISIONS 的论证细节**，只固化结论与不变量；不重复 ROADMAP 的进度，只描述架构。需要论证时指向 DECISIONS，需要进度时指向 ROADMAP。

---

# 第 1 部分 — 系统概览

## 1.1 项目目标

将一个**已存在的、能稳定跑赢手工调优的半自动 LLM 编译选项调优流程**，改造为**自主 Agent**，并增加结构化记忆。

已有的半自动流程：用户提供 Options List → LLM 挑选项组合 → 用户编译 → 跑 benchmark 打分 → 分数反馈 LLM → LLM 在历史上更新、给更优组合 → 循环至找到最优。

**Agent 化要解决的核心问题**：
- **记忆**：几百个 options、上百次历史，需要让 Agent 根据历史过滤（无效 option 不再考虑），避免浪费迭代。
- **经验注入**：支持注入代码技巧/项目经验（模块特定），但需校验防止错误经验污染。
- **自主运行**：Agent 自主跑动不需人工介入，但人工能看到进展（不黑盒）。
- **结构化可信判断**：在含噪 benchmark 环境下做可信的"候选是否更优"判断。

**关键背景（项目的存在性前提）**：用户已有的半自动流程**已经稳定跑赢手工调优**。本项目要验证的是：**自动化系统能否在低人工介入下复现/超越它**。这不是从零证明 LLM 能调优，而是把已验证有效的人在回路流程自动化 + 加结构化记忆。

## 1.2 部署形态

- **单机为主**：各开发者在自己设备（PC 或 Ubuntu 服务器）部署，无共享存储、无 NFS/SMB、无多人同时写同一份 memory。
- **团队共享靠文件互换**：experiences 通过 export/import 文件手动传递（A export → 发给 B → B import → B 本机验证/利用）。
- **gbs 裸机编译**：编译走 gbs（非 Docker），主要编 GCC/LLVM 相关代码，options 通过修改 spec 文件注入。
- **v1 仅支持 Linux/Ubuntu**。

## 1.3 核心设计哲学

这些原则贯穿所有组件，是架构的不可协商基线：

1. **用户可读可改记忆是 P0**。所有结构化记忆 + trace 落到用户能用 vim/VSCode 打开改的 yaml/markdown/jsonl。不能是黑盒（不塞 SQLite blob、不塞 vector store 作为唯一真相）。目的：防止 LLM 分析总结有误时用户能及时更正。

2. **Canonical state 永远在用户可见的文件里，框架内部状态只是 cache**。LangGraph 内部 checkpoint 是 cache_only，真相在外部 yaml/jsonl。框架可换、可重建，真相不丢。

3. **Agent 不直接选 combo**。决策走 Candidate Engine → Constraint Layer → Exploration Schedule 的确定性管线，LLM 只在候选生成的子策略里出现，不做最终裁决。

4. **保守诚实的统计判断**。在含噪环境下宁可给 inconclusive 也不给假 significant。决策级判断要么可信、要么诚实说不确定，绝不过度自信误导下游。

5. **所有破坏性写都有保护和审计**。spec backup/restore、workspace 保护、进程独立 group、原子写、trace 三层，破坏性操作可恢复、可追溯。

6. **模块隔离**。按模块隔离（Multimedia 的经验不能跑进 Chromium），通过配置 + 首次 init 问答确认实现。

## 1.4 全局架构

系统是**决策层 Agent + 执行层 Workflow + Skills** 的三层混合架构：

```
┌──────────────────────────────────────────────────────────────────┐
│              Orchestration Agent / LangGraph Loop                 │
│         (LLM-as-strategist: 仅高层策略, 不直接选 combo)           │
│   探索/利用切换 / 学习触发 / canary 调度 / dry-run 开关          │
│                         [待建: 09]                               │
└────────┬─────────────────────────────────────────────────────────┘
         │ 驱动决策循环
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Decision Core                             │
│  Candidate Engine (LLM proposal / local mutation / weighted rand)│
│        │ 产出候选 combo                                          │
│        ▼                                                         │
│  Constraint Layer (whitelist/exclude/failed-subset/exp/dedup     │
│        │            + 记录 rejected reason)                       │
│        ▼                                                         │
│  Exploration Schedule (窗口化多样性 + 复测预算统筹)             │
│                         [待建: 07; spike 7.0]                    │
└────────┬─────────────────────────────────────────────────────────┘
         │ 选定候选 → 交执行
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Inner Skill Workflow (确定性, 原子)           │
│  workspace_snapshot → spec_backup → spec_inject →                │
│  gbs_compile (new pgid) →                                        │
│      ├─[fail]→ err_analyze → spec_restore → ws_verify            │
│      └─[ok]  → benchmark → 产出 RunLevelRecord →                 │
│               spec_restore → ws_verify                           │
│                         [已建: 04/05/06 组件]                    │
└────────┬─────────────────────────────────────────────────────────┘
         │ RunLevelRecord (执行只产数据, 不做决策)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Statistics Core (纯裁决, 无副作用)              │
│   描述统计 / ESS+自相关诊断 / IID+block bootstrap /              │
│   baseline-candidate 比较 / verdict 门控 / pair_quality          │
│   ── 只 reads RunLevelRecord, returns StatisticalResult ──       │
│   ── 不写 FS-Memory; 决策与写入责任在 Decision Core/Workflow ──  │
│                         [已建: 08a]                              │
└────────┬─────────────────────────────────────────────────────────┘
         │ StatisticalResult → Decision Core 据此 accept/排序/继续探索
         │ (回到上方 Decision Core; 写入由 Decision Core/Workflow 执行)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                          FS-Memory                               │
│  SoT (YAML/MD/JSONL, 用户可读可改):                              │
│    kg/ trials/ failed_combos/ learned/ experiences/             │
│    baseline/ environment/ workspace_snapshots/                  │
│    trace/events.jsonl (canonical)                               │
│  Derived Index (可重建): _index.sqlite / vectors[默认关闭]      │
│  Recovery State: state/checkpoint.yaml / STOP / PAUSE           │
│                    [已建: 01/02/03]                              │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│   Observability: trace/events.jsonl (canonical) [已建: 03]      │
│   CLI status/report UX [待建: 10]                               │
└─────────────────────────────────────────────────────────────────┘
```

**读图要点（消除常见误读）**：
- **数据流是单向链**：Orchestration 驱动 → Decision Core 产候选 → Workflow 执行产 RunLevelRecord → Statistics Core 裁决产 StatisticalResult → Decision Core 据此决策 → 写 FS-Memory。
- **统计层不做决策、不写记忆**：Inner Skill Workflow 里的 benchmark 只产 RunLevelRecord；统计计算在 Statistics Core，但 accept/promote **决策只在 Decision Core (07)**；写 trial/KG/failed_combos 的责任在 Decision Core / Workflow，**不在 Statistics Core**。
- **LLM 边界**：Orchestration 的 LLM 只做高层策略（探索/利用、学习触发），Candidate Engine 的 LLM 只做候选提议；**两处 LLM 都不直接裁决，最终选 combo 走确定性管线**（见 §1.3 原则 3）。
- **07 vs 09**：07 建 Decision Core（候选引擎 + 约束 + 调度）；Orchestration Agent / LangGraph 循环在 09。07 不持有 LangGraph checkpoint。

**分层职责与 LLM 介入**：

| 层 | 职责 | LLM | 状态 |
|---|---|---|---|
| Orchestration Agent | 探索/利用切换、学习触发、dry-run 路由（仅高层策略） | ✅ 仅高层策略 | 待建 (09) |
| Candidate Engine | 多策略生成候选 | ⚪ 仅 LLM 子策略 | 待建 (07, spike 7.0) |
| Constraint Layer | 过滤非法/重复/高风险 + 记录 rejected reason | ❌ | 待建 (07) |
| Exploration Schedule | 窗口化保证多样性 + 复测预算统筹 | ❌ | 待建 (07) |
| Inner Skill Workflow | spec 保护 + workspace 保护 + 进程独立 group | ❌ (错误归因一次) | 已建 (04/05/06) |
| Skills | 原子能力（编译/benchmark/快照/校验） | ❌ | 已建 (05) |
| Statistics Core | 含噪环境可信统计裁决（无副作用、不写记忆） | ❌ | 已建 (08a) |
| FS-Memory | 文件系统 SoT + SQLite 派生索引 | ❌ | 已建 (01/02/03) |
| Observability | 本地 JSONL trace (canonical) | ❌ | 已建 (03; CLI UX 待 10) |

**LLM 越界防护**：Orchestration Agent 的 LLM 只参与高层策略（探索/利用切换、收敛响应、学习触发），**不直接生成 compiler option combo**；具体 combo 候选必须由 Candidate Engine 的确定性管线产出（提议 → 约束 → 调度）。这消解了"LLM-as-strategist"与原则 3"Agent 不直接选 combo"之间的表面张力。

**关键观察**：**支撑 07 的本地执行、保护、记忆、trace、统计基座已建**；**决策大脑（Decision Core / Orchestration）及 CLI/resume/dry-run/export/KG 治理等外围产品化能力待建**。已建成的层是上层将要消费的稳固地基。**整个价值命题（自主系统能否在低人工介入下复现/超越人在回路流程）目前押在未建的 07/09 上，而 05.5 spike 已把"noise-robust 二阶交互发现"标为全局头号风险**——最难、最不确定、决定项目成败的工作全在前方（见 §2.3 的 05.5 小节、§5.3 风险）。

---

# 第 2 部分 — 已建成的系统（8 个 Phase）

> 已完成 Phase（按关闭顺序）：01 → 02 → 03 → 04 → 06 → 05 → 08a。
> 注：实际开发顺序非数字顺序（06 先于 05），因为 05 的编译/benchmark skill 依赖 06 的进程管理。

## 2.1 基础层

### Phase 01 — Config / Init / Workspace Lock
项目初始化、module 隔离配置、workspace 锁。建立：配置文件 + 首次 init 问答确认 module 归属（防止跨模块经验污染）；workspace lock 防止同一 workspace 被并发 Agent 实例破坏；identifiers（trial/run ID 生成规则）。

**对外提供**：配置加载、module 隔离契约、workspace 租约。

### Phase 02 — FS-Memory SoT Writers
文件系统记忆的写入层。建立 SoT（Source of Truth）写入器：trials（immutable，trial 完成后一次性写、不再改）、failed_combos、learned rules、experiences、baseline、environment snapshots。

**核心不变量**：
- SoT 是 yaml/md（用户可读可改），SQLite 是**派生索引**（可从 SoT 重建）。
- trials 写后不可变（`TrialImmutableError` 守护）；运行中状态在 `state/checkpoint.yaml` 和 `trace/events.jsonl`，不在 trial 文件。
- 原子写（`atomic_write_yaml`）+ integrity hash（双层：source_integrity vs local_integrity）。

**对外提供**：SoT 读写、trial 记录、failed_combos 写入、integrity 校验。

### Phase 03 — Trace Lifecycle
可观测性的 canonical 真相。`trace/events.jsonl` 是 trace 的 SoT（不是 Langfuse，Langfuse 只是可选 viewer）。建立 trace 会话写入器、checkpoint 与 trace line count 对齐、会话 span 检查。

**核心不变量**：
- trace/events.jsonl 是 canonical SoT；分层 trace（决策/执行/记忆/评分）。
- checkpoint 与 trace 行数对齐可校验（崩溃恢复时确认状态一致）。
- token 消耗在 trace 中标注（无硬预算但要可见）。

**对外提供**：trace 会话写入、checkpoint-trace 对齐校验、会话 span 检查。

## 2.2 保护层

### Phase 04 — Workspace Protection Skills + CLI 骨架
裸机工作区保护的"中等策略 (b)"（用户明确要求，"这个真不能省，会出真事故"）。建立 workspace_snapshot（前后状态记录）、workspace_verify（检测非预期变化）、spec_backup/inject/restore（spec 文件保护）。CLI 入口骨架。

**核心不变量**：
- 中等策略 = spec backup/restore + 独立 build 目录 + artifact staging + 源代码状态记录但不强制干净。
- spec_restore 后 hash 不匹配 → `spec_corruption` → paused 等待人工。
- workspace_verify 检测到非预期变化（source_dirty_action=fail 时）→ `workspace_corruption`。

**对外提供**：workspace 快照/校验、spec 备份/注入/恢复。

### Phase 06 — Process Management
进程独立 group + 残留清理 + 监控。编译/benchmark 子进程以新 pgid 启动（隔离），多重校验清理残留进程。

**核心不变量**：
- 子进程新 pgid（process group 隔离），便于整组 kill。
- 残留进程清理多重校验：pgid + create_time + cmdline + env marker（防止误杀无关进程）；env 不可读时降级处理。
- 中断命令分层：pause/stop（trial 边界软停）/ abort-current（含清理）/ kill --force（hard kill 开发期 hang）。

**对外提供**：进程 spawn（新 group）、进程租约、清理（多重校验）、监控。

## 2.3 执行层

### Phase 05 — Compile / Benchmark Skills
编译与 benchmark 的原子 Skill。gbs 编译、错误分析归因、benchmark 打分、结果 schema。05.5 是 mock-only 集成可行性 spike（结论：集成管道可行，但 noise-robust 二阶交互发现是 07 头号风险，需经 7.0/08 处理）。

**核心数据结构 — RunLevelRecord**（执行层产出，统计层消费）：
- 单次 run 的记录：score、measured/warmup phase、valid_for_scoring、objective_direction、pair_key、started_at/ended_at、duration_sec、artifact 验证、env_snapshot、benchmark_cmd。
- 是执行层 → 统计层的契约载体。

**核心不变量**：
- benchmark 失败必须经 error_analyzer 归因：option_related → 写 failed_combos；infra_related → 不写、触发重试；unknown → 标 low_confidence 写。
- 05/08a 阶段 benchmark 不能写 failed_combos（`write_failed_combos=False` 强制）。
- valid_for_scoring=True 要求 artifact_hash_verified=True。
- 数值卫生：score 非有限（NaN/Inf）→ None → score_parse_failed（双重守护）。

**对外提供**：编译 skill、benchmark skill、错误归因、RunLevelRecord schema。

### Phase 05.5 — 集成可行性 Spike（已完成）
mock-only 集成可行性验证。**结论（对后续至关重要）**：集成管道（候选 → 编译 → benchmark → 统计 → 记忆）可行，但暴露了 **07 的头号算法风险**——**noise-robust 二阶交互发现**。Spike 实测：在 benchmark 噪声 σ=2.0 时，所有消融配置都塌到同一命中率，即**噪声会淹没 near-miss 信号**。这意味着 07 不能靠暴力搜索（搜索空间指数级）也不能天真比较（噪声淹没），必须有 noise-robust 的非暴力搜索策略 + 可信统计校正。这个风险认知是 7.0 spike 和 08a 统计核心存在的根本理由。findings 见 `dev_memory/spikes/05.5_integration_feasibility_findings.md`。

## 2.4 统计层

### Phase 08a — Statistics Core
纯统计核心（无副作用），是候选引擎做"候选是否更优"判断的基础。**统计核心经多轮外部专业 review（四个独立 AI）+ 大量数值坐实；其中 pair_quality 单独做了八轮对抗性加固**（每轮外部 AI 读代码跑探针找残留漏洞，Claude 数值坐实严重性，逐处修复 + 反向验证）。

**组件构成**：
- **描述统计**：均值、中位数、标准差、CV。
- **ESS + 自相关诊断**：有效样本量 `min(lag1_ESS, acf_ESS)`（保守）；自相关检测（lag-1 ρ>0.3）；趋势敏感的分段均值 ACF（drift 混合指标）。
- **Bootstrap**：IID percentile bootstrap（seeded）+ moving block bootstrap（自相关数据保留相关结构）。
- **比较**：baseline/candidate 比较，支持 paired（配对差分消除共模噪声）和 unpaired。
- **Verdict 门控**：AND 逻辑——判"显著"需 CI 排除 0 **且** 数据可信。
- **pair_quality**：配对质量评估（good/suspect/unknown）。
- **exploratory_signal**：非决策级探索信号。

**核心数据结构 — StatisticalResult**（统计层产出，候选引擎消费）：
关键字段：verdict、significant_single_comparison、ci_low/ci_high、effective_sample_size、autocorrelation_detected、paired、**pair_quality**、**exploratory_signal**、requires_confirmation、recommend_more_runs。

**核心不变量（八轮 review 固化，详见 §3.2）**：

1. **decision vs exploration 严格隔离**：decision-grade verdict 与 exploratory_signal 是严格隔离的双轨（详见 I-4）。unpaired+autocorrelation → 永远 inconclusive（时间混杂偏差，非样本量可解）。历史 unpaired 数据用 exploratory_signal（suggestive_*）排序/复测，但绝不进决策。schema 强制 `exploratory_signal != none → verdict 必 inconclusive`。

2. **只有 good pair_quality 能 decision-grade significant**。suspect/unknown 都降级。这防止"假配对（不同系统状态的两组被错误配对）伪装成高质量证据"。

3. **pair_quality 八轮加固收口两个 class**：
   - "信任时间元数据不核对"（1-6 轮）：所有衍生时间字段（pair_time_gap_sec、duration_sec）锚定 started_at/ended_at；双源取保守值 + 冲突检测；合并双臂时间线重叠检测。
   - "全局量耦合 per-pair 判断"（第 7 轮）：duration 阈值从全局 median 改为 per-pair `5×min(两 run 有效时长)`。
   - **封闭性论证**：per-pair 后，good 配对需 (a) 合并时间线无重叠 (b) pair_order 一致 (c) gap≤300s（started_at 锚定）(d) gap≤5×min(自身两 run 有效时长)。由 (a) 非重叠 ⟹ min(时长)≤gap，所以 duration 无法把 gap 容忍度撑过真实 gap，真实 gap 由 300s 上限锚定 started_at 封顶。

4. **固有边界**：所有时间元数据被一致、自洽、无重叠地伪造成小值（无任何物理/统计指纹）—— 统计内部原理上无法识别，属 trace 真实性/可信时钟范畴。**根本防线在 producer（7.0 诚实生成时间元数据）+ env_snapshot 交叉验证（08b）**，不是统计核心的职责。

5. **single_comparison 范围**：08a 只做单次比较，标记 single_comparison。多重比较校正需要全局比较族/计数，属 07 策略层。

6. **覆盖率回归锁定行为**：IID 覆盖率接近名义 95%、naive bursty 欠覆盖（~73%）、moving block 改善、detected-unpaired-autocorrelation 产出 0 个 decision-grade significant。

**对外提供**：`compare_run_records`（核心比较入口）、bootstrap CI、自相关诊断、描述统计。**这是候选引擎（07）消费统计判断的唯一入口——不要在 07 重新实现统计判断。**

---

# 第 3 部分 — 数据架构与核心不变量

## 3.1 FS-Memory 数据模型

FS-Memory 是整个系统的状态根基，分三类，职责严格区分：

**SoT（Source of Truth，用户可读可改）— YAML/MD/JSONL**：

| 路径 | 内容 | 可变性 |
|---|---|---|
| `kg/{version}/options/*.md` | 知识图谱：options 及元数据 | 版本化，merge 可追溯 |
| `kg/_op_log/`、`kg/_backups/` | KG 操作日志 + 备份（rollback 用） | 追加 |
| `trials/data/*.yaml` | 每次 trial 的完整记录 | **immutable**（完成后一次性写） |
| `failed_combos/*.yaml` | 已知失败的 option 组合 | 追加 |
| `learned/rules/*.yaml` | 学到的规则 | 追加/更新 |
| `experiences/*.yaml` | 注入的经验（唯一走 export/import 的） | 用户可加 |
| `baseline/baseline.yaml` | 基线配置 | 显式化 |
| `environment/snapshots/*.yaml` | 环境快照（硬失效字段 + 软上下文字段） | 追加 |
| `workspace_snapshots/*.yaml` | workspace 前后状态 | 追加 |
| `trace/events.jsonl` | **canonical trace SoT** | 追加 |

**Derived Index（派生，可从 SoT 重建）**：`trials/_index.sqlite`、`failed_combos/_index.sqlite`、`vectors/{kg,exp}.db`（v1 默认关闭）。

**Canonical Recovery State**：`state/checkpoint.yaml`、`state/STOP_REQUESTED`、`state/PAUSE_REQUESTED`。LangGraph internal checkpoint = cache only。

**共享范围**：只有 experiences 走 export/import。trials 不共享（与 commit/机器强绑定）、learned 不共享（跨机器意义不大）。

## 3.2 核心不变量汇总

这些是八轮 review + 各 phase 设计固化的不可协商约束，集中于此（论证细节在 `dev_memory/DECISIONS.md`）。每条标注类别：`[系统保证]` = 系统主动维持；`[范围边界]` = 声明某事不在本系统职责内。

**记忆与可读性**
- **I-1** `[系统保证]`：所有结构化记忆 + trace 落到用户可读可改的 yaml/md/jsonl。SQLite/vector 仅派生，可重建。
- **I-2** `[系统保证]`：Canonical state 在用户可见文件，框架内部状态仅 cache。**LangGraph internal checkpoint = cache_only**（9.0/9.1 的关键假设）。
- **I-3** `[系统保证]`：trials immutable（完成后一次性写）；运行中状态在 checkpoint + trace。

**统计可信性（08a，候选引擎消费契约）**
- **I-4** `[系统保证]`：decision-grade verdict 与 exploratory_signal 是**严格隔离的双轨**（非数学独立——两者从同一数据派生，但隔离消费）。`exploratory_signal != none → verdict 必 inconclusive`（schema 强制）；exploratory_signal 只用于排序/复测预算，不进 champion 决策。
- **I-5** `[系统保证]`：**unpaired + autocorrelation → 永远 inconclusive**（时间混杂偏差，非样本量可解）。
- **I-5b** `[系统保证]`：**unpaired + 非自相关（iid_assumption_valid=True）+ CI 排除 0 + 足够 power/ESS → 可以是 decision-grade significant**。（与 I-5 互补：unpaired 不是一律不可信，只有自相关时才封掉。）
- **I-6** `[系统保证]`：**对 paired 结果**，只有 `pair_quality=good` 才能 decision-grade significant；`suspect`/`unknown` 的 paired 结果降级为 inconclusive。（注意：本条只约束 paired 路径；unpaired 的 decision-grade 规则见 I-5/I-5b，不受 pair_quality 影响。）
- **I-7** `[系统保证]`：pair_quality 的所有时间判断锚定 started_at/ended_at（schema 强制 ended_at≥started_at），不信任可独立谎报的衍生字段（pair_time_gap_sec、duration_sec 双源/取保守值核对；合并双臂时间线重叠检测）。
- **I-8** `[系统保证]`：08a 只做 single_comparison。**多重比较校正在 07**（需要全局比较族/计数）。
- **I-9** `[范围边界]`：固有边界 = 全时间元数据被一致、自洽、无重叠地伪造（无物理/统计指纹）—— 统计内部原理上无法识别，**不在 08a 职责内**。兜底见 I-20（producer 诚实）+ 08b env_snapshot。**⚠ 时序缺口**：07（决策）早于 08b（env_snapshot 兜底），所以 **07 运行期间 I-9 的安全只靠 7.0 producer 一条**，env_snapshot 是更晚的加固。因此 I-20 是已欠的硬契约，不是远期支票。

**统计消费契约（决策层遵守）**
- **I-19** `[系统保证]`：决策层消费统计判断的**唯一入口**是 `compare_run_records` 及其返回的 `StatisticalResult`。decision-grade accept/promote 必须调用统计层提供的 `is_decision_grade(result)` / `can_accept(result)` helper（**helper 归统计层维护、决策层调用**），**禁止绕过 verdict 直接读 ci_low>0**。
- **I-20** `[硬契约]`：07 作为 producer **必须**生成真实的时间元数据（started_at/ended_at/duration_sec/pair_time_gap_sec）+ 真实的 paired AB/BA 组织。这是 08a 已按其发布的反面承诺（见 I-9），**不是 7.0 spike 的探索项，是 7.0 必须交付的硬契约**。
- **I-22** `[系统保证]`：任何进入统计比较的 score 必须绑定完整 provenance——exact combo、baseline identity、benchmark command/objective direction、source commit/artifact/env snapshot。否则统计层可能正确地比较了错误来源的数据。（**注**：现有 RunLevelRecord 尚未携带全部 provenance 字段如 source commit/baseline identity，I-22 是前瞻约束，相应字段需在 7.0/05 扩展 RunLevelRecord 时补上。）
- **I-25** `[系统保证]`：Statistics Core 是 side-effect-free 的纯裁决层——只 read RunLevelRecord、return StatisticalResult，**不写 FS-Memory、不做 accept/promote 决策**。写入与决策责任在 Decision Core/Workflow。（这是代码可验证的真属性，也是 §5.2 数值 review 方法成立的承重前提。）

**执行安全**
- **I-10** `[系统保证]`：破坏性写有保护审计（spec backup/restore、workspace 校验、原子写、integrity hash）。
- **I-11** `[系统保证]`：子进程新 pgid 隔离；残留清理多重校验（pgid+create_time+cmdline+env marker）。
- **I-12** `[系统保证]`：benchmark 失败经 error_analyzer 归因；只有 option_related 才写 failed_combos；infra_related 不写、触发重试；05/08a 阶段禁写 failed_combos。
- **I-13** `[系统保证]`：数值卫生——score 非有限 → None → score_parse_failed；valid_for_scoring 要求 artifact_hash_verified。
- **I-23** `[系统保证]`：中断/恢复控制面语义（见 §3.4）——pause（trial 边界软停）/ stop（优雅停）/ abort-current（带清理）/ kill --force（硬杀）四档分层；**checkpoint 与 trace 行数对齐可校验**（Phase 03 已建，崩溃恢复时确认状态一致）。

**决策约束（待 07/09 落地，但已定）**
- **I-14** `[系统保证]`：Agent 不直接选 combo，走 Candidate Engine → Constraint → Schedule 确定性管线。LLM 只在候选提议（Candidate Engine）和高层策略（Orchestration）出现，不裁决。
- **I-15** `[系统保证]`：rejected candidate 记录拒绝原因（matched_rule_id/path/filter_strength/penalty）；trace 只记实际生成/考虑的 rejected，不记理论组合空间。
- **I-16** `[系统保证]`：模块隔离（配置 + init 问答确认）。
- **I-17** `[系统保证]`：终止策略使用**配置化的最小实际收益阈值**（默认连续多轮无 ≥3% 改进即终止），**且不得基于 exploratory 或裸 noisy point estimate 单独终止**——必须基于 decision-grade evidence。**07 自带 baseline 停止判定**（"连续多轮无 ≥3% 改进"完全可由 08a 的 decision-grade evidence 算出，**不依赖 08b**）；**08b 的 convergence detector 是 additive 的进阶收敛判定**（更复杂的统计收敛信号），经 §4.2 的可插拔 adapter 被 07 消费，**不是 07 baseline 停止的前置依赖**。无论哪种，收敛是统计计算（08a baseline / 08b 进阶都产出 recommend），停止动作（搜索）始终由 07 执行（拆分见 §4.3）。
- **I-18** `[系统保证]`：**禁止未校正的 sequential peeking**（"测到显著为止"破坏覆盖率保证，单次比较级）；受控 sequential design 只能在 08b 通过明确 alpha/budget 规则引入。（与 I-17 不冲突：I-17 是搜索级终止"找不到更好的了"，I-18 是单次比较级禁止反复看数据提前判显著，作用层不同。）
- **I-21** `[系统保证]`：所有候选必须有 canonical representation 和 stable candidate_id；等价 option 组合不得重复评估或重复计入 multiple-comparison family（防 dedup/failed-subset/family 漂移）。**防重只针对 successfully evaluated + option_related 写入 failed_combos 的组合；infra_related 瞬态失败（OOM/磁盘满/网络抖动）不计入防重**（否则一次抖动可能永久错过最优解）。

**信任边界**
- **I-24** `[系统保证]`：单机部署下，export/import（Phase 12）是唯一跨机信任边界。imported experience 视为**不可信输入**——path traversal 防护、YAML safe_load、prompt injection（文本永远 quote）、tar member-by-member 抽取、双层 integrity（source vs local）、包大小/文件数/压缩率上限。

## 3.3 关键数据流与契约

**执行 → 统计 → 决策的核心链路**：

```
Inner Skill Workflow (执行, 不决策)
   │ 产出 RunLevelRecord (每次 run: score/phase/pair_key/时间戳/artifact验证/env)
   │ 必须绑定完整 provenance (I-22)
   ▼
Statistics Core (08a, 纯裁决, 不写记忆)
   │ compare_run_records(baseline_records, candidate_records)
   │ 产出 StatisticalResult (verdict/pair_quality/exploratory_signal/CI/ESS...)
   │ 提供 can_accept()/is_decision_grade() helper (I-19; 待建, 随 7.0 API 冻结交付)
   ▼
Decision Core (07, 待建)
   │ 消费 StatisticalResult 决定:
   │   accept/promote champion  ← 仅 paired+good+significant (I-6) 或 unpaired+IID+significant (I-5b)
   │                              且经 objective direction + practical threshold +
   │                              multiple comparison correction + confirmation policy
   │   排序/复测                 ← exploratory suggestive (I-4); 触发 paired 确认测试
   │                              (落在 Exploration Schedule + Proposers)
   │   继续探索                  ← inconclusive
   ▼
FS-Memory: Decision Core/Workflow 写 trial (immutable) + 更新 KG/failed_combos/learned
           (统计层不写, I-19/写入责任在调用方)
```

**消费契约要点（07 必须遵守）**：
- **统计层是纯 decision support，不写 FS-Memory**；写 trial/decision/rejection reason/KG update 的责任在 Decision Core/Workflow。
- 只用 `compare_run_records` 的 StatisticalResult 做判断，不重新实现统计。
- `significant_single_comparison` **不是**最终 accept 条件。07 的 accept 必须同时经过：pair_quality（paired 路径）/ IID（unpaired 路径）、objective direction、practical threshold、multiple comparison correction、confirmation policy。
- 必须用统计层 `can_accept()` helper，不绕过 verdict 直读 ci_low（I-19）。
- exploratory suggestive → 触发 paired 确认测试，是"从探索升级为决策"的流，落在 07 的 Exploration Schedule + Proposers。

## 3.4 中断 / 恢复控制面

REQUIREMENTS §3.3 把"中断/暂停/恢复生命周期"作为顶层概念。本系统的控制面跨多个 phase，统一视角如下（不变量见 I-23）：

| 控制 | 语义 | 边界 | Phase |
|---|---|---|---|
| `pause` | trial 边界软停（当前 trial 跑完才停） | 不中断进行中的 benchmark | 06 |
| `stop` | 优雅停（保存 checkpoint） | trial 边界 | 06 |
| `abort-current` | 中断当前 + 清理（spec restore + 进程清理） | 立即 | 06 |
| `kill --force` | 硬杀（开发期 hang 死兜底） | 立即，可能留残留待 doctor 清 | 06 |
| `resume` | 从 checkpoint 恢复 | checkpoint-trace 行数对齐校验（I-23） | 10 |
| `doctor` | 健康检查 + 残留清理 + 状态一致性修复 | — | 10 |

**关键恢复不变量**：checkpoint 与 trace/events.jsonl 行数对齐可校验（Phase 03 已建）——崩溃恢复时确认状态一致，benchmarking 阶段不能假设 spec 已 restore（按 §4.11.3 / §3.3.3 处理）。

---

# 第 4 部分 — 后续系统（待建 Phase 的架构设计）

> 本部分是 HLD 级别：定义组件职责、接口契约、关键约束，**不下到可实现的详细设计**。每个 phase 真正开始时，再像 08a 那样做冻结设计 + 外部 review。这是为了避免"边写文档边设计"。**唯一例外是 7.0 producer 契约**（见 §4.1）——因 08a 已按它发布（I-9/I-20），它不是"将来再设计"的留白，而是已欠的硬契约，应现在钉具体。

## 4.1 Phase 7.0 — 候选搜索策略 + 约束 Solver Spike

**性质与拆分**：原 7.0 混了两类工作，**已拆分为 7.0-contracts（契约冻结，先做）+ 7.0-spike（scaling 实测，后做）**：

**7.0-contracts（已冻结 v4，见 `doc/PHASE_7.0_CONTRACTS_DRAFT.md`）**：07 候选引擎的输入地基契约。经三轮十二份外部 AI review 收敛冻结。10 项契约 + 7 项代码交付：
- **契约 1 Canonicalization**（I-21）：**commutative-only search-space + value flag 显式建模**（`-O2/-O3` 建模成 `opt_level` value flag 取唯一值，避免 last-wins flag 排序"错合并"）；candidate_id = canonical 表示 hash（修 compute_combo_hash，两处入口统一）。
- **契约 2 Producer**（I-20）：时间元数据真实 + AB/BA（PRNG 流抽/配对间交错/blocked 平衡）+ 300s 上限 + pair_time_gap 语义（`abs(started_at 差)`）。
- **契约 3 Family**（I-8）：**FDR-BH screen（q=0.10，verdict 判方向，m=预注册全候选）+ confirmation-before-promote 两层**；family 预注册（每候选一 primary analysis，按 planned role 计数）。
- **契约 4 Fixed-budget**：固定 N（ESS-based）不依赖 08b adaptive；champion 每对新鲜重测的预算。
- **契约 5 Accept API**（I-19）：三层——`family_screen`(batch BH) / `is_decision_grade`(纯统计 property) / `can_accept`(per-candidate, AcceptDecision)；practical 判 `relative_ci_low_pct`（非 ci_low，单位对齐）。
- **契约 6 Baseline**：**champion updates baseline + 当轮配对重测**（绝不用历史存值，否则环境漂移违反 I-5）。
- **契约 7-10**：provenance 扩 RunLevelRecord（plan-owns）/ MeasurementPlan / LLM protocol / 单目标 v1。
- **代码交付**：修 compute_combo_hash（identity 变更，greenfield）+ 加 p_value + 相对 CI 字段 + family_screen/is_decision_grade helper + 扩 provenance + MeasurementPlan + AcceptDecision。前 5 项 additive 不动 08a 判定规则。

**7.0-spike（待做）**：
- **Scaling 实测**：constraint solver 在 10³/10⁴/10⁵ combos 的 runtime/memory 基准 → fallback 决策（10⁴ solve >30s → fallback；内存 >1GB@10⁵ → flag）。
- **搜索策略决策**：把 05.5 的"noise-robust 二阶交互发现"风险变成 07 具体搜索需求。
- **Power simulation**：用 08a 门控常量（MIN_VALID=10/AUTOCORRELATED=60）定契约 4 的固定 N。

**产出**：契约冻结（已完成）+ scaling 基准 + fallback 决策 + 固定 N 标定 → 喂给 07。

## 4.2 Phase 07 — 候选引擎 + 约束 + 调度（Decision Core）

**性质**：完整决策大脑（10-16 subtasks），**最大算法风险**。依赖 02/03/05.5/08a/7.0。**不依赖 08b**（只消费 08a；08b 是后续增强）。

**组件构成**：

| 组件 | 职责 | LLM |
|---|---|---|
| LLM Client | 可配置 LLM 接入（protocol + mock + kimi） | — |
| Candidate Proposers | 多策略候选生成：LLM proposal / local mutation / weighted random | ⚪ 仅 LLM 子策略 |
| Constraint Layer | 过滤：whitelist/mutual-exclusion/failed-subset/exp-soft-hard/dedup + 记录 rejected reason | ❌ |
| Exploration Schedule | 窗口化保证多样性 + **复测预算循环统筹** | ❌ |

**关键约束**：
- Agent 不直接选 combo（I-14）；走 proposer → constraint → schedule 确定性管线。
- 消费 08a：accept 走 §3.3 契约（paired+good 或 unpaired+IID，且经 practical threshold + multiple comparison + confirmation）。
- **复测预算循环归 07**：08a/08b 只给 `recommend_more_runs=True`（建议），由 07 的 Schedule 层决定是否放入复测队列。08b 不持有执行死循环（控制流归属见 §4.3）。
- LLM 可配置（商用模型未定，测试用 kimi）。
- schedule_slot 与 candidate_source 解耦（避免 quota 计数歧义）。
- 多重比较校正在此层（I-8）；禁 sequential peeking（I-18）。
- 07 不持有 LangGraph checkpoint，只读写 canonical SoT（I-2）。
- 07 通过 adapter 调用统计层，对 08b 的 adaptive rerun/outlier 模块保持"可插拔"（不直接依赖 08b 内部）。

**头号风险**：noise-robust 非暴力搜索 + LLM 集成（三者耦合：噪声下的非暴力搜索 + LLM 提议 + 统计校正）。05.5 已证明 σ=2.0 时噪声淹没 near-miss。7.0 spike 把风险从"未知"降到"可量化"，但不为零，07 仍需大量 review。

## 4.3 Phase 08b — 高级噪声策略

**性质**：3-4 subtasks，08a 的进阶。依赖 08a。**07 不依赖 08b**——08b 是增强路径，被 07/09 消费。可与 07 并行/之后。

**组件**：adaptive rerun（自适应重测）、outlier policy、noise diagnostics、sequential（受控序贯检验，非 peeking）、convergence detector（收敛判定）。

**关键职责与边界**：
- **env_snapshot_distance**：作为更强的 pair_quality 信号——直接对比配对内环境快照（cpu_freq/thermal）差异。这是 I-9 固有边界的部分兜底（**注意时序：它晚于 07**）。
- **收敛判定拆分**（解决 I-17 归属）：**07 自有 baseline 停止**（基于 08a decision-grade 的 ≥3% 停滞规则，不依赖 08b）；**08b 增加 additive 进阶 convergence detector**（更复杂统计收敛信号，经 §4.2 可插拔 adapter 被 07 消费）。两者都只产 recommend，**停止动作（搜索）始终由 07 执行**。08b 不是 07 停止的前置依赖。
- adaptive rerun：低 power 时**建议**追加测量（`recommend_more_runs`），**执行循环归 07 的 Schedule**（08b 不持有死循环）。
- 受控 sequential design（spending function），非"测到显著为止"。

**对 08a 的修改约束**：08b 对 pair_quality 的增强以**新增辅助信号/诊断为主（additive）**，**不修改 08a 已固化的 good/suspect/unknown 判定规则**；如需修改，必须走 08a 的回归 review（否则 07 已按 08a 语义实现，会回改）。

## 4.4 后续 Phase 概览

| Phase | 职责 | 依赖 |
|---|---|---|
| 9.0 | LangGraph Skeleton Spike | 07 |
| 9.1 | Canonical Ownership Spike（验证 LangGraph 内部状态 = cache_only，I-2） | 9.0 |
| 09 | LangGraph Workflow Orchestration（Orchestration Agent 落地） | 9.0/9.1/07/08b |
| 11 | Experience Injection + Canary（经验注入 + 校验，canary build_only 防"过滤了 option 永远不被证伪") | 02/07/09 |
| 12 | Export / Import（完整防御，I-24） | 02/11 |
| 13 | Recipe Export + Final Report（报告脱敏：api_key/home/host/env） | 09 |
| 14 | KG Management（版本管理 + merge 安全 + rollback） | 07/11/12 |
| 15a | Dry-run Skeleton（guard + forbidden writes + mode tagging） | 09 |
| 15b | Dry-run Full（mock skills + config validation + decision path） | 15a |
| 10 | CLI + Resume + Doctor（完整语义：中断分层 + 崩溃恢复 + 健康修复） | 09/15a |
| 16 | Integration + Real Env | 全部 |
| M_v1_minimal | v1-minimal 验收门 | — |

**Orchestration Agent（决策大脑顶层）在 09 落地**——消费 07 的 Decision Core、08a/08b 的统计、调度 dry-run，是 §1.4 架构图最顶层那一框。9.0/9.1 是它的前置 spike（验证 LangGraph 骨架 + canonical ownership，I-2）。

**07 与 experience 的边界**：07（Candidate Engine）只用本地已有 memory/KG 做约束（failed_combos/learned/exp soft-hard）；experience 的 import（11/12）在 07 之后，07 不触发 import 流程。

---

# 第 5 部分 — 治理

## 5.1 Phase 依赖与顺序

```
已建: 01 → 02 → 03 → 04 → 06 → 05 (+05.5 spike) → 08a
                                                    │
下一: 7.0-contracts (done: 07 输入契约冻结 v4) + 7.0-spike (scaling/strategy 探索)
        │
       07 (Decision Core: 候选引擎; 只消费 08a, 不依赖 08b) ──┐
        │                                                     │
      08b (高级噪声: env_snapshot/收敛/adaptive; 增强路径) ───┤
        │ (08b 可与 07 并行/之后; 07 不等 08b)                │
      9.0 → 9.1 (LangGraph spike)                             │
        │                                                     │
       09 (Orchestration Agent 落地; 依赖 07 + 08b + 9.0/9.1)◄┘
        │
      11 → 12 → 14 (经验/共享/KG)
      13 (报告) / 15a → 15b (dry-run) / 10 (CLI/恢复, 依赖 09/15a)
        │
       16 (真实环境集成) → v1-minimal 验收
```

**关键依赖说明**：
- **07 只消费 08a，不依赖 08b**（08b 是增强，07 用 conservative 08a 先做）。
- **09 依赖 07 + 08b + 9.0/9.1**（Orchestration 消费 08b 的进阶收敛/噪声策略；07 自有 08a-baseline 停止不需等 08b）。
- **08b → 09 是真实依赖**（不是 07→08b 串行）。

**为什么这个顺序**：底层先行（记忆/trace/保护/进程/编译/统计），决策大脑后建（消费底层）。08a 在 07 之前（07 消费统计判断）。7.0-contracts 先冻结 07 输入契约；7.0-spike 再量化 scaling/fallback 与固定 N，二者共同喂给 07。

## 5.2 质量门禁

每个 phase 遵循高保障闭环：

```
Codex 实现 → patch 三件套 + DECISIONS 条目 + REVIEW_NOTES 自审
   → Claude review (数值坐实/独立验证)
   → review-fix 循环
   → Ubuntu 验证
   → sync commit
```

统计代码的 review 方法 = 数值模拟（已知真值序列、独立重实现公式、覆盖率研究、对抗探针）。08a 的八轮 pair_quality 加固是这个方法的极致——外部 AI 读代码跑探针找残留，Claude 数值坐实严重性，逐处修复 + 反向验证。

## 5.3 待决事项与风险

**全局头号风险**：整个价值命题（自主系统能否在低人工介入下复现/超越人在回路流程）目前押在未建的 07/09 上。05.5 已把"noise-robust 二阶交互发现"标为头号算法风险——最难、最不确定、决定项目成败的工作全在前方。7.0 spike 先探（scaling/fallback + 搜索策略），把风险从"未知"降到"可量化"，但不为零。

**已识别的架构关注点**：
- I-9 时序缺口：07 早于 08b，07 期间固有边界只靠 7.0 producer（I-20）一条腿兜。必须在 7.0 把 producer 契约钉具体。
- 07 noise-robust 非暴力搜索 + LLM 集成是最大算法风险。

**记录待办（非阻塞，留 08b/07）**：
- env_snapshot_distance 作为更强 pair_quality 信号（08b）。
- 并发 worker 按 worker_id groupby（当前单机不触发）。
- 0.15-0.3 边界自相关梯度处理。
- ESS Geyer pair-sum/IMS 升级（当前 min(lag1,acf) 够用）。
- cosmetic：pair_order vs started_at 先后交叉核对（inert，非洗白向量）。
- AB/BA 集合层平衡检查（当前 per-pair）。

## 5.4 文档维护

本 HLD 是架构真相，随重大结构变化更新（phase 拆分/合并、架构调整、新增不变量）。日常进度记 `dev_memory/ROADMAP.yaml`，日常决策记 `dev_memory/DECISIONS.md`，本文档只在架构层面变化时更新。版本号随重大结构变化递增。

---

**END OF HLD v1.3**

> v1.1 修订（基于四份外部 AI review v1.0）：架构图加流向/分清 07-Decision-Core 与 09-Orchestration/标注统计层不写记忆；I-4 改"严格隔离"；I-6 限定 paired + 新增 I-5b（unpaired+IID 可 significant）；I-17 澄清防重排除瞬态失败 + 与 I-18 作用层；新增 I-19（消费入口单一+helper 归统计层）/I-20（producer 硬契约）/I-21（canonical id）/I-22（score provenance）/I-23（中断语义+checkpoint-trace 对齐）/I-24（导入不可信）；收敛判定拆分；07 不依赖 08b 显式声明；补齐依赖表；加 05.5 spike 小节 + 控制面小节。
>
> v1.2 修订（基于四份外部 AI review v1.1）：① 修 I-17 与"07⊥08b"的措辞张力——明确 07 自有 08a-baseline 停止（不依赖 08b），08b convergence 是 additive 进阶（§4.3/§5.1 同步）；② 修文档漂移——status v1.0→v1.2、§2.4 残留"正交"→"严格隔离"、15a 依赖 —→09；③ helper 在 §3.3 标"待建（随 7.0 交付）"；④ I-22 注明 provenance 字段需 7.0/05 扩 RunLevelRecord；⑤ 新增 I-25（统计层 side-effect-free 显式不变量）；⑥ §4.1 注明 7.0 scope 估算偏乐观、契约冻结量大应重估。
>
> v1.3 修订（基于 7.0-contracts v4 冻结）：§4.1 将 7.0 明确拆为 7.0-contracts（已冻结 v4，07 输入契约基线）+ 7.0-spike（scaling/strategy 实测）；概括 canonicalization / producer / family / fixed-budget / Accept API / baseline / provenance / MeasurementPlan 等契约要点，并指向 `doc/PHASE_7.0_CONTRACTS_DRAFT.md`；§5.1 同步依赖图与治理顺序。
