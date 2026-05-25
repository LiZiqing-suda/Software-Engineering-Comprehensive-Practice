import os
import sys
import config
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
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
BGE_LOCAL_PATH = "/data/gj/lzqrjgc/bge-small-zh-v1.5"
VECTOR_DB_PATH = "./vector_db_suda"
TOP_K = 15

# 全局资源
client = None        # DeepSeek 客户端
vectordb = None

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
    valid_docs = []
    for doc in raw_docs:
        content = doc.page_content.lower()
        if any(k in content for k in ["绩点", "gpa", "成绩", "分数", "奖学金", "学位", "毕业", "推免", "参评"]):
            valid_docs.append(doc)
    priority_docs, other_docs, graduate_docs = [], [], []
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
    try:
        data = await request.json()
        user_query = data.get("query", "").strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="请输入有效的问题")
        result = answer(client, vectordb, user_query)
        return {"code": 200, "data": {"answer": result}, "msg": "success"}
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
