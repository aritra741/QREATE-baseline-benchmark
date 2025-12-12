# join 语义操作补齐功能设计与实施计划

## 背景与目标
- 现状：`run_sql_on_gt` 直接用 duckdb 执行 SQL，Join 需要精确匹配，导致多表场景下 `gold_result` 行数偏少，影响评测准确率。
- 目标：新增“精确 + 语义 Join”可选模式，在不破坏现有默认行为的前提下，通过语义补齐扩大 Join 命中行，并保持后续指标计算流程不变。
- 范围：仅作用于 GT 执行阶段（`gold_result` 生成），对预测结果的匹配与指标计算逻辑不改；支持 Select/Filter/Join/Agg/Mixed 中的 inner join（等值条件）。

## 主要思路（分治执行链路）
1. 解析 SQL 为 Filter / Join / Aggregation 子步骤，确定各表的投影列、过滤条件、Join 键、Group By 列。
2. 每个表先在 duckdb 内执行 Filter（确定性），得到经清洗的子表。
3. 依次按 Join 图做“精确 Join + 语义 Join”：
   - 先跑标准等值 Join 得到 `exact_join_df`。
   - 将行数多的一侧的 Join 列送入向量库（document），另一侧的 Join 列作为 query，使用 seekdb 做向量预检索（topK 可配），再用 LLM 做逐条匹配确认，如果已经在 `exact_join_df`中则跳过，最终生成 `semantic_pairs`。
   - 将`semantic_pairs`与 `exact_join_df` 合并，得到补齐后的 Join 结果。
4. 若 SQL 含聚合，使用 duckdb 对补齐后的表执行标准 group by / aggregation。
5. 输出 `gold_result` 与现有文件命名保持一致，新增的调试产物可选落盘。

## 设计约束与假设
- Join 仅处理等值条件（`=` 或 `ON a.col = b.col`），不覆盖非等值/子查询/窗口函数。
- 支持多表串联 Inner Join（按解析出的 Join 图从基表开始逐边合并），暂不考虑全外连接。
- Join 列类型：优先处理字符串列；数值列默认走精确匹配，不做语义补齐；多列 Join 以“列值串联 + 描述”作为语义向量内容。
- 语义补齐是“增量 Union”策略：精确 Join 结果保留，语义匹配仅新增补齐行，避免破坏精确性。
- 性能：向量检索 topK、LLM 逐条确认，需可配置限流；超出行数阈值可提前退出或只做采样。

## 新增配置开关（EvalSettings / CLI）
- `semantic_join.enabled`：是否开启语义补齐（默认 False）。
- `semantic_join.topk`：向量检索返回候选数（默认 5/10）。
- `semantic_join.score_threshold`：向量相似度阈值（低于直接丢弃，减少 LLM 调用）。
- `semantic_join.llm_provider` / `semantic_join.llm_model`：语义匹配 LLM；默认沿用评测 LLM，支持单独指定。
- `semantic_join.max_query`：单次语义匹配的最大 query 数（防爆量，默认基于行数阈值）。
- `semantic_join.debug_dir`：可选调试落盘目录（候选对、LLM 判定）。
- `semantic_join.vector_prefilter_enabled`：是否先用向量检索做候选预过滤（默认 True，关闭则直接用 LLM 判定所有潜在 pair，需配合 `max_query`/采样保护）。
- CLI 新增：`--semantic-join`（布尔）、`--semantic-join-topk`、`--semantic-join-threshold`、`--semantic-join-max-query`、`--semantic-join-llm-provider/--semantic-join-llm-model`、`--semantic-join-vector-prefilter`（布尔）。

## 模块与职责拆分
- `SqlParser` 扩展：输出 Join 图（边列表、顺序）、每表 Filter 子句、必要的投影列；补充 Join 列的类型与列描述。
- `SemanticJoinPlanner`（新）：接收解析结果与各子表 DataFrame，按 Join 图生成执行计划（基表选择、Join 顺序、需要构建向量索引的列）。
- `SeekDBClient`（新）：按照 `ref_demo_code/database/oceanbase/demo8_hybrid_search_seekdb.py` 思路，重构一个简单的向量构建和检索模块，提供 `build_index(docs) -> index_id`、`search(index_id, queries, topk)` API，内部完成 embed -> 存储 -> 检索，匹配完成后可以选择是否删掉向量表。
- `JoinLLMMatcher`（新）：基于列描述/表名构造 prompt，对候选对做逐条判定；支持缓存与并发控制。
- `SemanticJoinExecutor`（新）：执行“精确 Join -> 语义补齐 -> 去重合并”，返回 DataFrame；对多列 Join 使用串联文本 `"{col1} [SEP] {col2}"` 作为向量内容。
- `GtRunner` 扩展：在 `run(sql, semantic_settings=None)` 内分支；`semantic_settings.enabled=False` 走原 duckdb 路径，开启时调用分治链路（Filter -> Semantic Join -> Aggregation）。

## 执行流程细化
1. **SQL 解析**：抽取 `tables`、`select_cols`、`filters_per_table`、`joins`（[(left_table, left_keys), (right_table, right_keys)]）、`group_by`、`aggregations`。
2. **Filter 阶段**：对每张表生成 `SELECT {join_keys + group_by + select_cols} FROM {table} WHERE {filter}` 的子 SQL，在 duckdb 中执行，结果 DataFrame 清洗并类型规范化。
3. **Join 阶段（逐边）**  
   - 基表选择：默认以最小行数子表为起点，按 Join 图顺序合并。  
   - 精确 Join：用 pandas/duckdb 做等值 inner join，得到 `exact_df`。  
   - 语义候选生成（可切换向量预过滤）：  
     - 若 `vector_prefilter_enabled=True`：统计左右表行数，行数多者为 document 侧，构造 `doc_text = join_col_values`（多列串联）；SeekDB 入库 document 列，记录向量 id -> 表主键(join的情况下主键都是{table_name}.id)索引映射；query 侧取 `query_text`，按 topK 检索并过滤相似度阈值，得到候选对。  
     - 若 `vector_prefilter_enabled=False`：跳过向量检索，直接对所有潜在 pair（受 `max_query`/采样控制）交给 LLM 判定。  
   - LLM 判定：对候选对构造 prompt（含列描述、表名、原值），LLM 返回是否匹配；通过者形成 `semantic_pairs`。  
   - 合并：`result_df = exact_df ∪ semantic_join_df`，按主键去重（以 exact 优先）。  
4. **Aggregation 阶段**：若存在 group by/聚合，使用 duckdb 在 `result_df` 上执行标准 SQL。  
5. **输出与调试**：  
   - 主输出仍为 `gold_result.csv`。  
   - 若开启 debug，则落盘 `semantic_candidates.csv`（候选对 + 分数）、`semantic_hits.csv`（LLM 通过的对），便于复现。

## 参考的代码
可直接复用的embedding类： @benchmark/evaluation/tools/text_embedding.py


## 风险与防护
- **爆量匹配**：设置 `max_query`、限制候选行数，超过阈值可只做精确 Join 或采样。  
- **误匹配污染**：LLM prompt 必须含列描述/示例，默认 exact 行优先保留；可选置信度阈值。  
- **性能**：复用向量索引（同表同列可缓存），批量检索，LLM 并发/重试可配置。

## 开发与测试计划
1. 扩展 `EvalSettings`、CLI 参数，打通 `GtRunner` 分支调用。  
2. 完成 `SqlParser` 的 Join/Filter 拆解输出，编写 `SemanticJoinPlanner`/`Executor` 框架与 SeekDB/LLM 适配层。  
3. 在 Player 数据集构造小型 Join 用例（如 city/team/manager），对比开启/关闭语义模式的 `gold_result` 行数差异。  
4. 添加单测：Join 图解析、向量候选生成、精确+语义合并去重逻辑。  
5. 集成冒烟：`--semantic-join` 跑一条多表 SQL，全链路生成 `gold_result.csv` 并校验文件结构。  
6. 文档：在 `use_manual.md` 补充开关说明与性能参数建议，引用 seekdb 依赖要求。

```
最终集成测试

python3 -m evaluation.run_eval \
  --dataset Player \
  --task Mixed \
  --sql-file evaluation/demo_acc_result/Player/Mixed/mixed_queries_filter_join/2/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Mixed/mixed_queries_filter_join/2/filter_join_player_2.csv \
  --semantic-join \
  --semantic-join-topk 8 \
  --semantic-join-threshold 0.25 \
  --semantic-join-max-query 20000 \
  --semantic-join-vector-prefilter


```
