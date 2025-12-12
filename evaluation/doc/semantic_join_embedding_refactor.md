当前直接用python进行暴力语义相似度匹配，对于行数不多的table来说速度也不错，但是当行数多了以后就最好切换成向量数据库来执行这个工作。
@todo benchmark/evaluation/tools/semantic_join.py 中的SeekDBClient 需要使用实际的seekdb进行重构。
可参考的seekdb向量数据库的用法-(将其中的代码改写成一个小模块，作为向量检索的功能基座)： 
@ref_demo_code/database/oceanbase/demo8_hybrid_search_seekdb.py (对待匹配的document列使用混合检索)
@ref_demo_code/database/oceanbase/ob_create_database_sqlAlchemy.py(创建指定的数据库并获取对应的连接符，我们的测试脚本使用"uda-bench"这个数据库名)