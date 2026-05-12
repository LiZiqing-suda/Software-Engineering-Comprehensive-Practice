import os
import config  # 导入所有配置

# 离线模式，不联网下载任何模型
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from vllm import LLM, SamplingParams

# ======================== RAG 本地配置（仅向量库和Embedding路径，可移到config.py） ========================
BGE_LOCAL_PATH = "/data/gj/lzqrjgc/bge-small-zh-v1.5"
VECTOR_DB_PATH = "./vector_db_suda"
TOP_K = 10

# ======================== vLLM 初始化（所有参数来自config.py） ========================
def init_vllm():
    llm = LLM(
        model=config.MODEL_PATH,
        tensor_parallel_size=config.TENSOR_PARALLEL_SIZE,
        gpu_memory_utilization=config.GPU_MEMORY_UTILIZATION,
        dtype=config.DTYPE,
        max_model_len=config.MAX_MODEL_LEN,
        trust_remote_code=True
    )

    # 生成参数全部来自config.py
    sp = SamplingParams(
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
        top_p=config.TOP_P,
        presence_penalty=config.PRESENCE_PENALTY,
        frequency_penalty=config.FREQUENCY_PENALTY,
        stop=["<|im_end|>"],  # Qwen2.5 官方唯一停止符
        repetition_penalty=1.05
    )
    return llm, sp

# ======================== 加载向量库 ========================
def load_rag():
    print("正在加载本地向量库...")
    embeddings = HuggingFaceEmbeddings(
        model_name=BGE_LOCAL_PATH,
        model_kwargs={"local_files_only": True}
    )
    vectordb = Chroma(
        persist_directory=VECTOR_DB_PATH,
        embedding_function=embeddings
    )
    print("✅ 向量库加载完成")
    return vectordb

# ======================== RAG 检索 + 智能过滤（解决本科生/研究生混淆） ========================
def get_context(vectordb, query):
    raw_docs = vectordb.similarity_search(query, k=TOP_K)
    
    # 1. 过滤完全无关文档
    valid_docs = []
    for doc in raw_docs:
        content = doc.page_content.lower()
        # 只保留和问题相关的文档（绩点/成绩/奖学金/学位等）
        if any(k in content for k in ["绩点", "gpa", "成绩", "分数", "奖学金", "学位", "毕业", "推免", "参评"]):
            valid_docs.append(doc)
    
    # 2. 智能优先级排序：本科生文档 > 其他 > 研究生文档
    priority_docs = []
    other_docs = []
    graduate_docs = []
    
    for doc in valid_docs:
        source = doc.metadata["source"].lower()
        content = doc.page_content.lower()
        
        if "本科" in source or "本科生" in content:
            priority_docs.append(doc)
        elif "研究生" in source or "硕士" in source or "博士" in source:
            graduate_docs.append(doc)
        else:
            other_docs.append(doc)
    
    sorted_docs = priority_docs + other_docs + graduate_docs
    
    # 3. 去重，最多保留前3个最相关文档
    seen = set()
    context_list = []
    for doc in sorted_docs[:3]:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            context_list.append(f"【来源：{doc.metadata['source']}】\n{doc.page_content}")
    
    return "\n\n".join(context_list)

# ======================== 问答逻辑（Qwen2.5 标准ChatML格式 + config提示词） ========================
def answer(llm, sp, vectordb, q):
    ctx = get_context(vectordb, q)
    
    # 严格遵循Qwen2.5 ChatML格式，系统提示词来自config.py
    prompt = f"""<|im_start|>system
{config.PROMPT_TEMPLATE.format(context=ctx, user_query=q)}<|im_end|>
<|im_start|>user
{q}<|im_end|>
<|im_start|>assistant
"""

    output = llm.generate(prompt, sp)
    return output[0].outputs[0].text.strip()

# ======================== 主程序 ========================
if __name__ == "__main__":
    print("="*60)
    print("  苏州大学校园政策智能问答系统")
    print(f"  模型：{config.MODEL_PATH.split('/')[-1]} | 并行GPU：{config.TENSOR_PARALLEL_SIZE}")
    print("  输入 exit/quit/退出 结束程序")
    print("="*60)

    print("\n正在加载大模型与向量库，请稍候...")
    llm, sp = init_vllm()
    vectordb = load_rag()
    print("\n✅ 系统初始化完成！可以开始提问\n")

    while True:
        user_query = input("请输入你的问题：").strip()
        
        if user_query.lower() in ["exit", "quit", "退出"]:
            print("\n👋 感谢使用，再见！")
            break
        
        if not user_query:
            print("⚠️ 请输入有效的问题\n")
            continue
        
        print("\n🔍 正在检索政策文档并生成回答...")
        ans = answer(llm, sp, vectordb, user_query)
        print(f"\n💡 回答：\n{ans}\n")
        print("-"*60)
