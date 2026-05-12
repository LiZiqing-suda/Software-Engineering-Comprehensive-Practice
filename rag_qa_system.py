import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from vllm import LLM, SamplingParams

# ======================== 配置 ========================
MODEL_PATH = "/nvme/Qwen2.5-72B-Instruct"
BGE_LOCAL_PATH = "/data/gj/lzqrjgc/bge-small-zh-v1.5"
VECTOR_DB_PATH = "./vector_db_suda"
TOP_K = 5
TENSOR_PARALLEL_SIZE = 4
DEBUG_MODE = False  # 关闭调试，干净运行

# ======================== vLLM初始化 ========================
def init_vllm():
    llm = LLM(
        model=MODEL_PATH,
        tensor_parallel_size=TENSOR_PARALLEL_SIZE,
        gpu_memory_utilization=0.9,
        trust_remote_code=True,
        max_model_len=32768
    )
    sp = SamplingParams(
        max_tokens=2048,
        temperature=0.1,
        top_p=0.9,
        stop=["<|im_end|>"],
        repetition_penalty=1.05
    )
    return llm, sp

# ======================== 加载向量库 ========================
def load_rag():
    embeddings = HuggingFaceEmbeddings(
        model_name=BGE_LOCAL_PATH,
        model_kwargs={"local_files_only": True}
    )
    vectordb = Chroma(
        persist_directory=VECTOR_DB_PATH,
        embedding_function=embeddings
    )
    return vectordb

# ======================== RAG检索 ========================
def get_context(vectordb, query):
    docs = vectordb.similarity_search(query, k=TOP_K)
    res = []
    seen = set()
    for doc in docs:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            res.append(f"【来源：{doc.metadata['source']}】\n{doc.page_content}")
    return "\n\n".join(res)

# ======================== 问答函数 ========================
def answer(llm, sp, vectordb, q):
    ctx = get_context(vectordb, q)

    prompt = f"""<|im_start|>system
你是苏州大学校园政策智能问答助手。
1. 只能根据参考文档回答，严禁编造。
2. 无答案则回复：未查询到相关校园政策信息。
3. 条理清晰、简洁准确，直接给出答案。
4. 不生成问题、不反问、不续写、不重复。<|im_end|>
<|im_start|>user
参考文档：
{ctx}

用户问题：{q}<|im_end|>
<|im_start|>assistant
"""

    output = llm.generate(prompt, sp)
    return output[0].outputs[0].text.strip()

# ======================== 主程序 ========================
if __name__ == "__main__":
    print("="*60)
    print("  苏州大学校园政策问答系统")
    print("  输入 exit 退出")
    print("="*60)

    llm, sp = init_vllm()
    vectordb = load_rag()
    print("✅ 加载完成，可以开始提问！")

    while True:
        q = input("\n请输入问题：").strip()
        if q.lower() in ["exit", "quit", "退出"]:
            print("👋 再见！")
            break
        if not q:
            continue

        ans = answer(llm, sp, vectordb, q)
        print(f"\n💡 回答：\n{ans}")