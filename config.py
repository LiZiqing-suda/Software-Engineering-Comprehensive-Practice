# ========================
# vLLM + Qwen2.5 推理配置
# ========================

# 模型路径（你自己改成服务器上的真实路径）
MODEL_PATH = "/nvme/Qwen2.5-72B-Instruct/"

# vLLM 推理参数
TENSOR_PARALLEL_SIZE = 4        # GPU 数量，单卡就填 1
GPU_MEMORY_UTILIZATION = 0.9    # 显存占用比例
DTYPE = "auto"                  # 精度自动：bf16 / fp16
MAX_MODEL_LEN = 32768           # Qwen2.5 最大长度

# 生成参数
MAX_TOKENS = 4096
TEMPERATURE = 0.1
TOP_P = 0.9
PRESENCE_PENALTY = 0.0
FREQUENCY_PENALTY = 0.0

# RAG 问答系统提示词模板
PROMPT_TEMPLATE = """
你是苏州大学校园政策智能问答助手。
请严格根据下面提供的参考文档回答，不能编造信息。
如果文档中没有答案，请直接回复：未查询到相关校园政策信息，请自行在学校网站寻找或咨询学校工作人员。
如果询问到绩点相关问题，必须慎重处理，区分是本科生还是研究生，数值必须在参考文档中寻找，请准确解析文档当中的markdown表格，找到正确的对应关系。
在最后输出“由AI生成，不保证结果的准确性，仅供参考，请仔细甄别”。

【参考文档】
{context}

【用户问题】
{user_query}

请回答：
"""
