# Software-Engineering-Comprehensive-Practice
软件工程综合实践项目，2327405045黎子卿，2327405060王玉。

校园智能问答助手。

使用RAG技术构建知识库，再使用大模型api进行推理。使用deepseekv4-flash模型的api进行推理，成本低，效果好，且上下文长度高，非常适合该任务。

核心修改：防攻击逻辑，单个源IP每分钟最多进行三次请求。
