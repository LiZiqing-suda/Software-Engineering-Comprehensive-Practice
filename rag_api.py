import os
import config
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from contextlib import asynccontextmanager
from multiprocessing import freeze_support

# 必须在最开头添加，解决多进程启动问题
freeze_support()

# 离线模式配置
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# 导入现有核心逻辑依赖
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from vllm import LLM, SamplingParams

# ======================== 全局配置 ========================
BGE_LOCAL_PATH = "/data/gj/lzqrjgc/bge-small-zh-v1.5"
VECTOR_DB_PATH = "./vector_db_suda"
TOP_K = 15

# 全局变量（用于存储初始化后的资源）
llm = None
sampling_params = None
vectordb = None

# ======================== 核心逻辑函数（完全复用原有） ========================
def init_vllm():
    llm = LLM(
        model=config.MODEL_PATH,
        tensor_parallel_size=config.TENSOR_PARALLEL_SIZE,
        gpu_memory_utilization=config.GPU_MEMORY_UTILIZATION,
        dtype=config.DTYPE,
        max_model_len=config.MAX_MODEL_LEN,
        trust_remote_code=True
    )
    sp = SamplingParams(
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
        top_p=config.TOP_P,
        presence_penalty=config.PRESENCE_PENALTY,
        frequency_penalty=config.FREQUENCY_PENALTY,
        stop=["<|im_end|>"],
        repetition_penalty=1.05
    )
    return llm, sp

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

def get_context(vectordb, query):
    raw_docs = vectordb.similarity_search(query, k=TOP_K)
    
    valid_docs = []
    for doc in raw_docs:
        content = doc.page_content.lower()
        if any(k in content for k in ["绩点", "gpa", "成绩", "分数", "奖学金", "学位", "毕业", "推免", "参评"]):
            valid_docs.append(doc)
    
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
    
    seen = set()
    context_list = []
    for doc in sorted_docs[:3]:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            context_list.append(f"【来源：{doc.metadata['source']}】\n{doc.page_content}")
    return "\n\n".join(context_list)

def answer(llm, sp, vectordb, q):
    if not q.strip():
        return "⚠️ 请输入有效的问题"
    ctx = get_context(vectordb, q)
    prompt = f"""<|im_start|>system
{config.PROMPT_TEMPLATE.format(context=ctx, user_query=q)}<|im_end|>
<|im_start|>user
{q}<|im_end|>
<|im_start|>assistant
"""
    output = llm.generate(prompt, sp)
    return output[0].outputs[0].text.strip()

# ======================== FastAPI 生命周期管理（关键修复） ========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化资源，关闭时释放资源"""
    global llm, sampling_params, vectordb
    print("=== 开始初始化全局资源 ===")
    try:
        # 初始化vLLM模型（现在在主进程启动后执行）
        llm, sampling_params = init_vllm()
        # 加载向量库
        vectordb = load_rag()
        print("=== 全局资源初始化完成 ===")
        yield  # 应用运行中
    except Exception as e:
        print(f"❌ 初始化失败：{str(e)}")
        raise e
    finally:
        # 应用关闭时清理资源
        print("=== 正在释放资源 ===")
        if llm is not None:
            del llm
        print("=== 资源释放完成 ===")

# FastAPI 实例化（使用lifespan管理生命周期）
app = FastAPI(
    title="苏州大学校园政策智能问答API",
    version="1.0",
    lifespan=lifespan
)

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# ======================== API接口 ========================
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/qa")
async def qa(request: Request):
    global llm, sampling_params, vectordb
    
    # 检查资源是否初始化完成
    if llm is None or vectordb is None:
        raise HTTPException(status_code=503, detail="系统正在初始化，请稍后再试")
    
    try:
        data = await request.json()
        user_query = data.get("query", "").strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="请输入有效的问题")
        
        result = answer(llm, sampling_params, vectordb, user_query)
        return {"code": 200, "data": {"answer": result}, "msg": "success"}
    except Exception as e:
        return {"code": 500, "data": {}, "msg": f"服务器错误：{str(e)}"}

# ======================== 启动服务 ========================
if __name__ == "__main__":
    uvicorn.run(
        app="rag_api:app",
        host="0.0.0.0",
        port=8080,
        reload=False,  # 必须关闭热重载，否则会导致多进程冲突
        workers=1      # 必须单进程运行，模型无法在多进程间共享
    )
