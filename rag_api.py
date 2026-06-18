import os
import sys
import time
import config
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from contextlib import asynccontextmanager
from multiprocessing import freeze_support

# 离线向量库仍使用 HuggingFace 本地模型，保留此设置
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

freeze_support()

from openai import OpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# ======================== 全局配置 ========================
BGE_LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bge-small-zh-v1.5")
VECTOR_DB_PATH = "./vector_db_suda"
TOP_K = 15

# 限流配置
RATE_LIMIT_MAX = 3       # 单IP每分钟最大请求数
RATE_LIMIT_WINDOW = 60   # 时间窗口（秒）

# 全局资源
client = None        # DeepSeek 客户端
vectordb = None

# 限流记录：{ip: [timestamp, timestamp, ...]}
_rate_limit_records = defaultdict(list)

# ======================== 初始化函数 ========================
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
    priority_docs, other_docs, graduate_docs = [], [], []
    for doc in raw_docs:
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
    for doc in sorted_docs:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            context_list.append(f"【来源：{doc.metadata['source']}】\n{doc.page_content}")
            if len(context_list) >= 3:
                break
    return "\n\n".join(context_list)

def answer(client, vectordb, q):
    if not q.strip():
        return "⚠️ 请输入有效的问题"
    ctx = get_context(vectordb, q)
    system_content = config.PROMPT_TEMPLATE.format(context=ctx, user_query=q)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": q}
    ]
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
        top_p=config.TOP_P,
        stream=False,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}}
    )
    return response.choices[0].message.content.strip()

def check_rate_limit(ip: str) -> tuple[bool, int, int]:
    """检查IP是否超过限流阈值。返回 (是否允许, 剩余次数, 重置剩余秒数)"""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    # 清理过期记录
    records = _rate_limit_records[ip]
    while records and records[0] < cutoff:
        records.pop(0)
    # 清理空条目
    if not records:
        del _rate_limit_records[ip]
        records = _rate_limit_records[ip]
    count = len(records)
    if count >= RATE_LIMIT_MAX:
        reset_sec = int(records[0] + RATE_LIMIT_WINDOW - now) + 1
        return False, 0, reset_sec
    return True, RATE_LIMIT_MAX - count - 1, 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, vectordb
    print("=== 开始初始化全局资源 ===")
    try:
        # 初始化 DeepSeek 客户端
        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )
        print("✅ DeepSeek 客户端初始化完成")
        # 初始化本地向量库
        vectordb = load_rag()
        print("=== 全局资源初始化完成 ===")
        yield
    except Exception as e:
        print(f"❌ 初始化失败：{str(e)}")
        raise e
    finally:
        print("=== 正在释放资源 ===")
        if client is not None:
            del client
        if vectordb is not None:
            del vectordb
        print("=== 资源释放完成 ===")

app = FastAPI(
    title="苏州大学校园政策智能问答API",
    version="1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/qa")
async def qa(request: Request):
    global client, vectordb
    if client is None or vectordb is None:
        raise HTTPException(status_code=503, detail="系统正在初始化，请稍后再试")

    # ===== 限流检查 =====
    client_ip = request.client.host if request.client else "unknown"
    allowed, remaining, reset_sec = check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "data": {},
                "msg": f"请求过于频繁，请 {reset_sec} 秒后再试（单IP每分钟最多 {RATE_LIMIT_MAX} 次）"
            },
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT_MAX),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + reset_sec)),
                "Retry-After": str(reset_sec),
            }
        )

    try:
        data = await request.json()
        user_query = data.get("query", "").strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="请输入有效的问题")
        result = answer(client, vectordb, user_query)
        # 记录本次请求
        _rate_limit_records[client_ip].append(time.time())
        return JSONResponse(
            status_code=200,
            content={"code": 200, "data": {"answer": result}, "msg": "success"},
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT_MAX),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(time.time() + RATE_LIMIT_WINDOW)),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        return {"code": 500, "data": {}, "msg": f"服务器错误：{str(e)}"}

if __name__ == "__main__":
    uvicorn.run(
        app="rag_api:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        workers=1
    )
