


# 完整测试流程demo

## step 1 : clone仓库并建立测试目录

```
git clone  https://github.com/DB-121143/UDA-Bench.git
cd UDA-Bench/
mkdir -p  evaluation/demo_acc_result
conda activate quest
```

## step 2 : 生成评测用sql和属性字典
指定1个类别的query并收集对应的sql语句+属性描述(以Player Join为例)：
```
python3 -m evaluation.sql_preprocessor \
  --dataset Player \
  --task Join \
  --sql-file Query/Player/Join/join_queries.sql \
  --attributes-file Query/Player/Player_attributes.json \
  --output-root evaluation/demo_acc_result 
```
上述脚本运行完后，可以得到下面的文件：
```
evaluation/demo_acc_result/Player/Join/join_queries/2/sql.json
evaluation/demo_acc_result/Player/Join/join_queries/3/sql.json
...
```
包含这类queries中每条Sql以及其对应的属性+类型+描述。

### template
通用的模板格式如下，根据你要测试的query类别修改对应`{}`中的参数即可。
```
python3 -m evaluation.sql_preprocessor \
  --dataset {数据集名} \
  --task {Task名} \
  --sql-file Query/{数据集名}/{Task名}/{query集合名}.sql \
  --attributes-file Query/{数据集名}/{数据集名}_attributes.json \
  --output-root evaluation/demo_acc_result 

```
其中，
{数据集名}：  路径Query/CSPaper ， Query/Med 中的最后一级, 比如CSPaper, Med。
{Task名}:  路径Query/Player/Filter , Query/Player/Join 中的最后一级, 比如Filter, Join。
{query集合名}:   路径Query/Player/Filter/filter_queries_city.sql 中的最后一级去掉后缀， 比如filter_queries_city。


## step 3 : 手动拷贝UDA系统跑出的query到评测目录
每个Query都要单独拷贝一次
将UDA系统跑出的对应编号的query结果拷贝到下面的路径中：
```
cp <PATH_TO_YOUR_RESULT>  evaluation/demo_acc_result/Player/Join/join_queries/2/result.csv
```

### template
通用的模板格式如下，根据你要测试的query类别修改对应`{}`中的参数即可。
```
cp <PATH_TO_YOUR_RESULT>  evaluation/demo_acc_result/{数据集名}/{Task名}/{query集合名}/{id}/result.csv
```
{id} 是这个query的编号，和{query集合名}.sql中注释的编号保持一致。

## step 4 : 完成评测
每个Query都要单独评测一次
调用评测脚本完成对这条query的评测
```
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Join \
  --sql-file evaluation/demo_acc_result/Player/Join/join_queries/2/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Join/join_queries/2/result.csv
```

### template

```
python3 -m evaluation.run_eval \
  --dataset {数据集名} \
  --task  {Task名}  \
  --sql-file evaluation/demo_acc_result/{数据集名}/{Task名}/{query集合名}/{id}/sql.json \
  --result-csv evaluation/demo_acc_result/{数据集名}/{Task名}/{query集合名}/{id}/result.csv
```

### 可选：开启语义 Join 补齐
在 GT 执行阶段加入语义 Join 扩充（默认关闭），常用参数如下：
- `--semantic-join`：启用语义补齐。
- `--semantic-join-topk`：向量预检索候选数。
- `--semantic-join-threshold`：向量相似度阈值。
- `--semantic-join-max-query`：限制进入语义匹配的 query 行数，避免爆量。
- `--semantic-join-vector-prefilter/--no-semantic-join-vector-prefilter`：是否启用向量预筛。
- `--semantic-join-llm-provider/--semantic-join-llm-model`：语义判定使用的 LLM，可覆盖全局配置。

示例（基于 Player Mixed 的 filter_join 用例）：
```
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Mixed \
  --sql-file evaluation/demo_acc_result/Player/Mixed/mixed_queries_filter_join/2/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Mixed/mixed_queries_filter_join/2/filter_join_player_2.csv \
  --semantic-join \
  --semantic-join-topk 8 \
  --semantic-join-threshold 0.35 \
  --semantic-join-max-query 200 \
  --semantic-join-vector-prefilter
```

## step 5 : 查看评测结果
评测结果会出现在：evaluation/demo_acc_result/Player/Join/join_queries/2/acc_result
包括
```
├── acc.json ： 逐列-平均准确率
├── gold_result.csv : sql在该数据集上的Player-GT大表上执行后的结果
├── matched_gold_result.csv
└── matched_result.csv ： 系统跑出的result和gold_result能match上的行。
```

### template
```
evaluation/demo_acc_result/{数据集名}/{Task名}/{query集合名}/{id}/acc_result
```
