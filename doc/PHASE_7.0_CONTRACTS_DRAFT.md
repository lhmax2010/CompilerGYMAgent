# Phase 7.0-contracts — 契约冻结设计草案 v4（FROZEN）

> **状态**：v4（已冻结）。v1→四份review→v2(拍板)→四份review→v3(补接缝)→四份review→v4(末梢)。三轮共十二份外部 AI review，四份一致"可冻结"。本版为 07 候选引擎的输入契约冻结基线。
> **定位**：把 HLD §4.1 (B) 类硬契约展开 + 四份 review 补出的遗漏，定义 07 候选引擎开工前必须冻结的输入地基。08a 已按其中部分发布（I-20/I-9），定错会导致 07 返工。
> **冻结流程**：v2 → 最终 review（确认拍板落地 + 无新矛盾）→ 冻结为 HLD 级契约 + 写 DECISIONS + 必要时扩 08a/schema → 07 据此实现。
> **不在本草案**：scaling 实测/fallback 决策（7.0-spike，后做）；07 算法实现（proposers/mutation/prompt 设计，留 07）。

## 拆分背景

7.0 原是单 spike，但混了两类工作：(A) scaling/strategy 探索（测了才知道→7.0-spike，后做）+ (B) 硬契约（想清楚才能定→本草案 7.0-contracts，先做）。先做 (B) 因为：① I-20 producer + I-9 时序缺口是 08a 已欠契约；② (A) 的 scaling 需要 (B) 的 canonicalization 才测得准；③ (B) 大部分纯设计。

## v1→v2 关键变更（四份 review + 拍板）

四份 review 揭示草案 v1 两个**方向性错误**（非遗漏）+ 一个最重要遗漏 + FDR 现状缺口。v2 拍板：
1. **[拍板] Family**：FDR-BH screen + **confirmation-before-promote** 两层（FDR 不承重，确认门防假冠军）。
2. **[拍板] Baseline**：**champion updates baseline + 当轮配对重测**（不用历史存值）。← v1 最重要遗漏。
3. **[拍板] p-value**：**08a 加 p_value 字段**（FDR 需要 p 排序；08a 当前只产 CI）。
4. **[拍板] Canonicalization**：**commutative-only search-space + value flag 显式建模**（不盲目排序去重——避免 last-wins flag 的"错合并"）。← v1 方向性错误修正。

---

# 契约 1 — Candidate Canonicalization（I-21）

## v1 的方向性错误（已修正）
v1 建议"排序+去重后 hash"。**坐实的 combo_hash bug 是真的**（result_schema.py:364，`"\0".join(combo)` 顺序敏感+不去重），但 v1 的修复方案本身有更危险的 bug：

- **漏合并（安全方向）**：`[-O2,-flto]` vs `[-flto,-O2]` 本是同一组合，hash 不同 → 重复评估（浪费）。
- **错合并（危险方向）**：`[-O2,-O3]` vs `[-O3,-O2]` 排序后都变 `[-O2,-O3]` → 同一 hash，**但编译产物不同**（last-wins：哪个 -O 生效取决于顺序）→ 两个语义不同的组合被当成同一个 candidate → 决策灾难。

排序去重对 last-wins/override/value flag（`-O2/-O3`、`-fx/-fno-x`、`-march=x/-march=y`）会制造错合并。错合并比漏合并危险得多。

## 拍板：commutative-only search-space + value flag 显式建模
v1 search-space 限定为**可证明排序安全**的形式：

1. **Option 分类**（search-space 定义的一部分）：
   - **commutative bool flag**：独立开关，顺序无关（如 `-flto`、`-funroll-loops`）。排序去重安全。
   - **value flag**：建模成 `key → value`（如 `opt_level → {O0,O1,O2,O3}`、`march → {native,armv7,...}`）。canonical 表示取该 key 的**唯一值**（搜索空间里一个 key 只能有一个值，不存在 `-O2 -O3` 共存）。
   - **互斥组**：声明互斥的 flag 集合，Constraint Layer 判非法（不进 canonicalization）。
2. **Canonical 表示**：`(sorted(commutative bool set), sorted(key=value pairs))` → 唯一表示。
3. **candidate_id**：canonical 表示归一化后 hash（**修复 compute_combo_hash**：先归一再 hash，幂等 `canonical(canonical(x))==canonical(x)`）。
4. **last-wins/override 不进 v1 搜索空间**：要搜 `-O2` vs `-O3`，建模成 `opt_level` value flag 取一个值，不是两个 bool flag 共存。
5. **option taxonomy 是 trust-critical 工件**：每个 flag 的 commutative/value/互斥分类**必须对照编译器文档验证**（v2 把风险从"排序错"搬到"分类声明错"——若某顺序敏感 flag 被误声明 commutative，又回到错合并）。curated 小集合下可控，但要显式 own + 校验。
6. **多值/累加 flag 出 v1 搜索空间**：`-D/-I/-Wl,`、`--param x=N` 等多值/列表 flag 破坏"key→单值"模型，**不在 v1 搜索空间**；若需搜索须先建模为 value flag 并定义等价规则。

## 与 08a/已建的关系
- **compute_combo_hash 必修**（P0）：当前顺序敏感+不去重。修法 = 先实现 search-space aware `canonicalize_candidate(spec, combo)`（按 taxonomy 归一），`compute_combo_hash` 只 hash canonical representation（不是单纯排序 list——函数当前只收 `list[str]`，不知哪些 commutative/value）。
- **这是 identity 语义变更，不是 additive**：改变 identity-hash 输出（非 canonical 顺序的 combo hash 会变）。不动 08a 统计判定规则（这点对），但已持久化的 combo_hash/failed_combos 会与新 hash 不匹配。**已确认 greenfield**（仓库无持久化 combo_hash，仅测试 fixture 用单元素 combo→排序去重无操作→hash 不变），无需迁移。
- **【代码交付要点】两处 hash 入口必须统一**：`compute_combo_hash` 现有**两份实现**（`result_schema.py:364` + `fs_memory.py:1179`，后者被 TrialRecord 用于校验 hash）。修复时两处必须委托**同一个 `canonicalize_candidate` / canonical hash helper**，不能分叉——否则一处 canonicalize 一处不，TrialRecord 的 combo_hash 校验会失败。
- 这定义了"同一个 candidate"——直接影响 I-21 防重、failed_combos 去重、family 计数。
- **去除首尾/统一内部空白**（防 `-O2 ` vs `-O2` 脏输入），**不改大小写**（gcc/llvm flag 大小写敏感）。

## 留后（明确）
- 等价 flag 展开（`-O2` 隐含子 flag）v1 不做——这是**漏合并（安全方向）**，可 defer 到 KG（14）。前提：curated option set 不含同义异形（不能同时有 `-O2` 和它的手工展开作为两种写法）。

---

# 契约 2 — Producer 契约（I-20，已欠硬契约）

## 责任划分（四份确认准确）
08a 八轮 pair_quality 全建立在时间元数据真实的前提上。08a 能验证**时间不一致指纹**（overlap、gap-vs-duration 冲突、双源冲突），但**全字段自洽伪造**（把 1000s 间隔标成相邻、所有时间戳一致造假）08a 原理上抓不了（I-9 固有边界）。所以：08a 验证一致性指纹；**producer 自律保证真实性**；08b env_snapshot 部分物理兜底（晚于 07，I-9 时序缺口）。

## 07 作为 producer 必须保证
1. **时间元数据真实**：started_at/ended_at 真实墙钟（单调时钟，禁事后回填/重写）；duration_sec ≤ ended−started；pair_time_gap_sec 与 started_at 推导一致。
   - **pair_time_gap_sec 语义精确定义**：08a 用 `abs(started_at_candidate − started_at_baseline)`（两 run 起点差），**不是** idle gap（前 run ended 到后 run started）。producer 必须按此语义填，否则被 08a 判 source_conflict。
2. **配对时间邻近 + 落入 good 区间**：pair_time_gap 同时满足 ≤ `max(5×min(duration), 5s FLOOR)` **且 ≤ 300s 绝对上限**（PAIR_QUALITY_GAP_ABS_MAX_SEC）。慢 benchmark 也不能超 300s。
3. **AB/BA 组织**：
   - **每对独立随机顺序**：pair_order 由 `hash(session_seed, candidate_id, baseline_id, pair_index)` 决定（PRNG 流抽），**禁固定 ABAB 交替模式**（防与 bursty 噪声周期 aliasing）。
   - **blocked randomization 整批平衡**：baseline_first 比例 ≈ 50%（偶数 N 精确 50/50，奇数差 1）。失衡 trace 告警但不 rerun（不破坏 paired 设计）。这是 08a "AB/BA 集合层平衡"待办的 producer 义务。
   - **配对间交错（interleaving）**：baseline/candidate run 时间上交错，**不能 baseline 全上午、candidate 全下午**——否则跨对的系统性时间漂移污染配对差分（pair_quality 只查 per-pair gap，跨对漂移是盲区）。
4. **pair_key 规则**：每个 pair_key 恰好 one baseline + one candidate；两条记录 pair_order 一致。
5. **RunLevelRecord 最小字段集**：每条 record 必填项（07 实现时定，含下方 provenance）。

## 与 baseline 契约耦合
producer 怎么配对依赖 baseline 定义（契约 6）——baseline run 与 candidate run **当轮配对生成**（同期交错测量），不是历史存值。

---

# 契约 3 — Multiple-Comparison Family（I-8）

## v1 的错误（已修正）
v1 写"只计 decision-grade 比较"——**错**。这会"看到结果才决定纳不纳入校正"（只算 significant 的），低估多重比较、放大假阳性。

## 拍板：两层结构（FDR screen + confirmation promote）
**不让单一校正扛 promote**：
- **第一层 — 轮内 FDR-BH screen**：一轮内所有候选用 Benjamini-Hochberg（q=0.10 默认可配）筛出"值得确认"的。FDR 在共享 baseline 的正相关 p 值下（PRDS）有效。
  - **只筛改善方向（objective-aware）**：双侧 p 会让强 regression 也 p 很小。screen 用 **`verdict == significant_improvement`** 判方向（08a 已按 objective_direction 正确构造 verdict——higher_is_better 与 lower_is_better 都对；**不要用 `relative_effect_pct > 0`**，那只对 higher_is_better 成立，会漏 lower_is_better 的真改进）。
  - **FDR 的 m = 预注册 family_size（全候选）**：BH 分母 m 锚定预注册候选数，**不缩成"改善方向子集"**（数据依赖的 m 是 v1 计数 bug 的变体）。方向过滤只用于"regression 不被 discover"，不改 m。等价的更干净实现：用**单侧改善 p**（regression 自动得大 p、永不 discover，m 天然保持全候选）。
  - **FDR 会 over-discover 欠功效比较**（某 low-power inconclusive 的 bootstrap p 偶然很小能过 BH）——这正好被第二层接住（进 confirmation 复测，要么补足 power 变真显著、要么被揭穿）。所以两层对欠功效 over-discovery 稳健；**screen 不要求只喂过 power 门的 p**。
- **第二层 — confirmation-before-promote**：screen 过的候选不直接晋升，必须 **paired 确认测试 + 以 margin 击败当前 champion**。真正防假冠军的是确认门，不是校正强度。

## family 定义
- **边界**：一轮 + 一 benchmark + 一 objective = 一个 family。
- **family 必须预注册**：family_id、候选集合、planned_family_size 在**测分前冻结**（否则 07 可"一候选一轮"把 size 变 1 绕开校正）。
- **family size 计数（按 planned role，非 observed result）**：每个预注册 screen family 中，**每个候选有且只有一个预注册 primary analysis**，family_size = 候选数。计数规则：
  - infra 补测/低 power 重测 **替换同一 primary analysis**（**填到预注册 planned N 为止、不超过**——靠契约 4 固定预算约束，非"加到显著"的 optional-stopping，不擦边 I-18），不新增假设。
  - exploratory（触发确认用，planned role 非决策）**不进 family**。
  - confirmation 是**独立 confirmation plan/gate**，**不回写减少 screen family 计数**。
  - 计入 primary analysis 实际进入统计检验的结果（significant + no_difference + inconclusive-with-valid-data），无有效数据的 inconclusive 不计（没真做检验）。
  - 关键：family 成员由**预注册时的候选清单**决定，不由结果决定——堵死 v1 的"看结果才决定纳不纳入"。
- **跨轮不累计**：跨轮是序贯优化（champion 每轮被 re-validate），由 confirmation-before-promote + champion re-validation（+ 未来 I-18 受控序贯）控制，**不靠把每轮 family 切小逃避 alpha**。跨轮假晋升有归属，不是"不归我们管"。

## p-value 缺口（拍板：08a 加 p_value）
FDR-BH 需要 p-value 排序，但 08a 当前只产 CI（StatisticalResult 无 p_value）。**拍板：08a 加 p_value 字段**——bootstrap 分布算双侧 p（对 paired 差分 δ：`2×min(P(δ<0), P(δ>0))`）。
- **zero-count correction**：用 `(k+1)/(B+1)` 避免 bootstrap p=0（k=尾侧计数，B=bootstrap 次数）。
- **与 CI/verdict 自洽**：从同一 bootstrap_effects 分布算（与 percentile CI 同源同尾），95% CI 排除 0 ⟺ p<0.05（近似）。是改 stats_core（CI 函数算完 bootstrap 分布加 `count/B` 穿进 StatisticalResult），不只是 schema 加字段。additive（不动判定规则）。
- **p_value 是诊断，不得绕过 power 门**：欠功效比较可 p<0.05 但 verdict=inconclusive，靠"family 只在 confirmation 后晋升"保证。

---

# 契约 4 — Fixed-Budget Minimal Schedule

## 拍板：固定预算（不依赖 08b adaptive）
07 在 08b 之前用固定 paired budget，不自适应。

1. **固定 N 对 paired/候选**（N 由 7.0-spike 的 power 分析定）。
2. **N 按 ESS 算，非裸 pair 数**：paired 差分序列仍可能自相关（08a 会检测），达到 power 所需的 N_pairs 可能远大于裸 n 门槛。契约写"N 使 **ESS**（非裸 n）清门"。
   - 对齐 08a 门控常量：`MIN_VALID_FOR_SIGNIFICANCE=10`、`AUTOCORRELATED_MIN_VALID_FOR_SIGNIFICANCE=60`。7.0-spike 用这些做 power simulation 定 N。
3. **固定预算下 power 不足**：08a 给 `recommend_more_runs=True` 时，07 默认动作是**降级 inconclusive / 入复测队列**，**不自动加测**（自动加测是 08b adaptive）。这样固定预算承诺才硬。
4. **复测预算循环归 07**（HLD I-17）：08a/08b 只给 recommend，07 Schedule 决定是否复测。
5. **预算含每对一次新鲜 champion run**（契约 6 耦合）：因 baseline=champion 且必须当轮配对时间邻近，champion 不能一轮测一次配所有候选（后面候选与那次 champion 测量时间不邻近→pair_quality 判 gap 过大）。所以 champion 为**每一对**重测：一轮内 champion 被测 `N_candidates × N_pairs` 次。固定预算要把这个**翻倍含义**算进去（每对 = 一次 candidate run + 一次新鲜 champion run）。

---

# 契约 5 — Accept API（I-19，归统计层）

## 拍板：三层接口（family_screen batch / is_decision_grade 纯统计 / can_accept per-candidate）

**FDR-BH 是 batch-level（对全族 p 排序找阈值），不能塞进 per-candidate 的 can_accept**——FDR 拒绝阈值 `p_(k) ≤ q·k/m` 依赖该候选在族中的 p 排名，单候选不知自己的 rank。所以拆三个：

1. **family_screen(results: list[StatisticalResult], *, method, q) -> list[bool]**（归统计层，batch）：
   - 对全族 p_value 排序做 BH，返回每个 result 是否被 screen 选中。
   - 只读 p_values + verdict（筛改善方向用 `verdict==significant_improvement`，m=全候选，见契约 3）。归统计层与 I-19"统计判断入口统一"一致。
   - **输入 results 必须属于同一预注册 family**（07 按 family 分组后传入，不混不同 family）。
2. **is_decision_grade(result) -> bool**（归 08a，纯统计 property）：
   - `verdict ∈ {significant_improvement, significant_regression}` 且路径合规：`paired → pair_quality=good` / `unpaired → iid_assumption_valid`。
   - （删 v2 的"且 not low_power"——significant verdict 按 08a 构造已不可能 low_power，冗余。）
   - **必须从 schema 校验器同一个谓词派生**（单一真相源），不独立重实现"什么是决策级"，否则与 verdict 门哪天分叉就不一致。
3. **can_accept(result, *, is_family_screened, confirmation_status, practical_threshold_pct, objective_direction) -> AcceptDecision**（per-candidate，统计层骨架 + 07 注入策略）：
   - 只做 confirmation + practical threshold 门（family screen 已由 #1 batch 处理，这里传入 `is_family_screened` 布尔）。
   - 返回 **AcceptDecision dataclass**（非 bool），原因码：`accepted / rejected_insignificant / rejected_pair_quality / rejected_not_screened / rejected_practical_threshold / rejected_relative_threshold_unavailable / needs_confirmation / rejected_incomplete_provenance`。
   - **practical threshold 单位修正**：判 **`relative_ci_low_pct > practical_threshold_pct`**（相对改进 CI 下界 > 阈值百分比），**不是 ci_low**（ci_low 是原始 score 单位，与 3% 阈值单位错配）。需 08a 加 `relative_ci_low_pct/relative_ci_high_pct` 字段（见 checklist）。schema 强制 `relative_ci_low_pct ≤ relative_effect_pct ≤ relative_ci_high_pct`（与 ci_low≤point_estimate≤ci_high 一致）。
   - **baseline≈0 退化情形**：baseline_mean≈0 时 relative_effect_pct/relative_ci_low_pct 为 None（与现有 relative_effect_pct is None 行为一致）→ can_accept 返回 `rejected_relative_threshold_unavailable`（不能用 None 判阈值）。
   - **provenance 执行点**（契约 7 连接）：decision-grade 要求 provenance 完整，否则 `rejected_incomplete_provenance`——让 I-22 有牙（否则"schema 可选 + 契约要 07 填"无强制）。
   - 08a 不硬编码 3%/family 策略，只校验 + 用传入参数。

## 禁绕过（I-19）
07 必须用 helper，禁绕过 verdict 直读 ci_low（约定 + code review 强制）。

## practical_threshold 与 I-17 的 3% 关系（拍板：同一阈值）
**默认同一阈值，配置化**：accept 需 `relative_ci_low_pct > practical_threshold_pct`；stop（I-17）是连续 K 轮无 candidate 被 accept。默认 `practical_threshold_pct = 3%`（与 I-17 一致），可配置覆盖。逻辑自洽：能 accept 的改进一定打破停滞，不能打破停滞的轮次也不产生 accept。

---

# 契约 6 — Baseline 定义与更新（v1 最重要遗漏，四份一致）

## 拍板：champion updates baseline + 当轮配对重测
1. **baseline 是什么**：当前 **champion**（不是固定默认）。初始 champion = 项目默认选项。
2. **improvement 相对谁**：相对当前 champion（站在已有最好的基础上找下一个更好）。
3. **更新规则**：某 candidate 被 decision-grade accept 且满足 practical threshold + 通过 confirmation → 成为新 champion/baseline。
4. **【硬约束，四份一致】当轮配对重测 + 每对新鲜 champion run**：参与 decision-grade 的 baseline 数据**必须与 candidate 同轮配对生成**（同期交错测量），**绝不允许拿历史存值的 baseline 分数**与今天的 candidate 配对——bursty/环境漂移会让历史 baseline 过期，违反 I-5。进一步：champion **为每一对重测**，**不跨对复用 champion 测量**（一轮测一次 champion 配所有候选会让后面候选与那次 champion 时间不邻近→pair_quality 判 gap 过大）。预算含义见契约 4#5。
5. **champion 更新后**：family 重置（新参照系 = 新比较族）；旧 baseline 下的比较结果保留在 trial 历史，但不用于当前决策。
6. **baseline_identity provenance**：每次比较绑定当轮 champion 的 candidate_id（见契约 7）。

## 与其他契约的耦合
- 契约 2（producer）：baseline run 当轮配对重测。
- 契约 3（family）：champion 更新 → family 重置。
- 契约 5（accept）：accept 相对当前 champion。
- 契约 7（provenance）：baseline_identity = 当轮 champion id。

---

# 契约 7 — Provenance 字段扩展（I-22）

## 拍板：现在扩 RunLevelRecord（schema 可选字段，07 填）

**字段归属（解决契约 7/8 重叠，plan-owns 模型）**：candidate_id/family_id/baseline_id 的 **canonical 真相源是 MeasurementPlan（契约 8）**，RunLevelRecord **只带 `measurement_plan_id` 引用 + run 专属 provenance**，避免两个真相源漂移。

RunLevelRecord 加的字段（可选/nullable，对已建记录零破坏，07 填）：

| 字段 | 含义 | 归属 |
|---|---|---|
| `measurement_plan_id` | 指向所属 MeasurementPlan（candidate_id/family_id/baseline_id 从 plan 取） | **引用** |
| `source_commit` | 跑 benchmark 时的源码 commit | run 专属 |
| `benchmark_id` / `benchmark_version` | benchmark 脚本/版本标识 | run 专属 |
| `objective_id` | 目标标识（v1 单目标，见契约 10） | run 专属 |

- candidate_id/family_id/baseline_identity **不直接列进 record**（从 plan 解引用），或若为查询便利反规范化则**强制一致性不变量** `record 解引用 plan 的值必须相等`。**默认 plan-owns（record 只带 plan_id）更干净**。
- **provenance 执行点**（契约 5 连接）：decision-grade 要求 provenance 完整（plan_id 可解引用 + run 专属字段齐全），否则 `can_accept` 返回 `rejected_incomplete_provenance`——让 I-22 有牙。

I-22 要求 score 绑定完整 provenance——这些字段让"统计层正确比较了正确来源的数据"可验证。

---

# 契约 8 — MeasurementPlan（四份补）

## 一个可追踪的测量计划，而非散落在 run records
固定 N、pair_key 生成、AB/BA order、seed、candidate_id、baseline_id、family_id 应属于一个 **MeasurementPlan** 对象（可追踪、可复现、可审计）。**MeasurementPlan 是 candidate_id/family_id/baseline_id 的 canonical 真相源**（契约 7 的 record 只引用 plan_id）：
- `measurement_plan_id`、`family_id`、`candidate_id`、`baseline_id`（**canonical-owner**）
- `plan_type: screen | confirmation`（让契约 3 两层结构在数据上不混——screen 计入 family，confirmation 是独立 gate）
- `planned_n_pairs`、`abba_seed`、`pair_order` 序列
- `created_at`（family 预注册时间戳，契约 3 的"测分前冻结"）

trace 记录 plan，run records 引用 plan_id。plan 落 trace/SoT（与 I-1 可读 / I-2 canonical 在文件一致）。这让"family 预注册"和"AB/BA 可复现"有数据落点。

**plan-owns 的适用范围（carve-out）**：plan-owns 只适用于 **identity/config 字段**（candidate_id/family_id/baseline_id——08a 不消费的）。**measurement 字段**（pair_order/started_at/pair_key/pair_time_gap_sec——08a 从 record 读、实际消费的）**留 RunLevelRecord**；plan 持"计划值"（planned pair_order 序列），record 持"实测值"，**二者是"计划 vs 实际"非"同一真相两份"**，一致性可校验（审计实测是否按计划）。所以 plan 和 record 都有 pair_order 不是重叠 bug。

---

# 契约 9 — LLM Client / Proposer 协议（四份补）

## 可 mock 的 protocol（协议冻结，prompt 设计留 07）
- **输入**：prompt（含 history、options、module context）。
- **输出**：list of proposed combos（每个 combo = list of option strings）。
- **错误降级**：timeout / parse failure / 空返回 的处理策略。
- **【硬约束】LLM 输出走统一管线**：LLM 提议的候选必须经**同一条 canonicalization + constraint 管线**（契约 1 + Constraint Layer），不能让 LLM 直接吐绕过 canonical 形式的"候选"（I-14）。
- 具体 prompt 设计 / mutation 策略 / weighted random 实现留 07。

---

# 契约 10 — 单目标 v1 假设（四份补，界定 3/5）

## 显式声明：v1 单目标
契约 3 的 family（一 objective）、契约 5 的 accept 都默认单目标。**v1 显式声明单目标**（throughput 或 size 之一，objective_direction 已在 schema）。多目标（throughput + size 的 Pareto 权衡）留后续——若 v1 多目标，family/accept 结构大变。

---

# 开放/决策点（详细逻辑留 07，但原则现在标）

- **失败子集传播**（契约 1 耦合）：`[-O2,-flto]` 失败是否排除超集 `[-O2,-flto,-fx]`？low_confidence failed 怎么权重？**标为决策点**，详细留 07，但"失败子集是否传播到超集"原则影响剪枝激进度，07 开工要先定。
- **partial pair 处理**（契约 4/8）：infra_failure 导致半臂缺失，07 Schedule 是否在预算内补齐配对（最大化 pair_count/power）？建议：预算允许则重测缺失半臂。
- （practical_threshold 与 I-17 的 3% 关系**已拍板**：同一阈值、配置化、默认 3%，见契约 5。）

---

# 冻结 checklist

| 契约 | 核心决策 | 改 08a/schema? |
|---|---|---|
| 1 Canonicalization | commutative-only + value flag 建模 + taxonomy 验证 + canonicalize_candidate | 是（identity 语义变更，非 additive） |
| 2 Producer | 时间真实 + AB/BA(PRNG/交错/blocked) + 300s 上限 + gap 语义 | 否 |
| 3 Family | FDR screen(只筛改善方向)+confirm 两层 + 预注册(按 planned role) | 是（加 p_value + zero-count） |
| 4 Fixed-budget | 固定 N(ESS-based) + 不自动加测 + champion 每对重测预算 | 否 |
| 5 Accept API | family_screen(batch)+is_decision_grade(同源派生)+can_accept(AcceptDecision) + 判 relative_ci_low_pct | 是（加 helper + 相对 CI 字段） |
| 6 Baseline | champion updates + 当轮配对重测 + 每对新鲜 champion run | 否 |
| 7 Provenance | 扩 RunLevelRecord（plan-owns，record 只带 plan_id 引用 + run 专属） | 是（加字段） |
| 8 MeasurementPlan | plan 对象(canonical-owner) + plan_type + family 预注册落点 | 否（新结构） |
| 9 LLM protocol | 可 mock protocol + 走统一管线 | 否 |
| 10 单目标 | v1 单目标显式声明 | 否 |

**需改 08a/schema 的（5 项代码交付）**：
1. **修 compute_combo_hash → canonicalize_candidate**（契约1）：**identity 语义变更**（非 additive），改变 hash 输出；已确认 greenfield（无持久化 combo_hash）无需迁移；不动统计判定规则。
2. **加 p_value 字段**（契约3）：改 stats_core（从 bootstrap 分布算双侧 p + zero-count `(k+1)/(B+1)`），additive 不动判定。
3. **加 relative_ci_low_pct/relative_ci_high_pct 字段**（契约5）：解决 practical_threshold 单位错配（ci_low 是原始 score 单位，阈值是 %），additive。
4. **加 family_screen + is_decision_grade helper**（契约5）：family_screen batch 做 BH，is_decision_grade 从 schema 校验器同源派生，additive。
5. **扩 RunLevelRecord provenance**（契约7）：加 measurement_plan_id + run 专属字段（plan-owns），可选 nullable。

①是 identity 语义变更（greenfield 安全，**两处 hash 入口统一委托同一 canonical helper**），②③④⑤是 additive 不动 08a 判定规则。

**额外新代码交付（非 08a/schema 修改，但要写）**：
6. **MeasurementPlan**（契约 8）：新 pydantic 模型（plan_type/planned_n_pairs/abba_seed/pair_order/canonical-owner ids）+ 落 trace/SoT。
7. **AcceptDecision**（契约 5）：新 dataclass（带原因码）。
（checklist 表里这两项标"否（新结构）"指"非 08a 修改"，但它们仍是 7.0-contracts 要交付的新代码，别当文档概念漏实现。）

# 不在 7.0-contracts（明确留后）
- scaling 实测 + fallback 决策 → 7.0-spike
- 07 算法（proposers/mutation/weighted random/prompt）→ 07
- adaptive rerun / env_snapshot / 进阶收敛 → 08b
- 多目标 Pareto → 后续
- 等价 flag 展开 → KG（14）
