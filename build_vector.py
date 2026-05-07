import os
import re
import shutil

# 国内镜像加速
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

# ================= 核心配置 =================
INPUT_DIR = "./RAG提取结果_高精度"
PERSIST_DIR = "./vector_db_suda"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
REBUILD_FORCE = False  # 有库就不重建
TOP_K = 10  # 真正返回10条结果！


# ================= OCR文本清洗 =================
def clean_ocr_text(text):
    text = re.sub(r'-+\s*第\s*\d+\s*页\s*-+', '', text)
    text = re.sub(r'^\s*[-—]+\s*\d+\s*[-—]+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'抄送：.*?\n', '', text)
    text = re.sub(r'.*校长办公室.*印发.*\n', '', text)
    text = re.sub(r'\d{4}年\d{1,2}月\d{1,2}日印发', '', text)
    text = re.sub(r'\n\s*\n+', r'\n\n', text)
    text = re.sub(r'[-=—]{3,}', '', text)
    return text.strip()


# ================= 向量库构建 =================
def build_vector_db():
    print("=" * 50)
    print("🔹 首次构建向量库")
    print("=" * 50)
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME, model_kwargs={"device": "cpu"})
    documents = []

    for filename in [f for f in os.listdir(INPUT_DIR) if f.endswith(".md")]:
        with open(os.path.join(INPUT_DIR, filename), "r", encoding="utf-8") as f:
            clean_txt = clean_ocr_text(f.read())
        content = f"【来源文件：{filename}】\n{clean_txt}"
        documents.append(Document(page_content=content, metadata={"source": filename}))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=350, chunk_overlap=50,
        separators=["\n第三条", "\n第二条", "\n第一条", "\n（一）", "\n（二）", "\n1.", "\n\n", "。"]
    )
    split_docs = splitter.split_documents(documents)
    vectordb = Chroma.from_documents(documents=split_docs, embedding=embeddings, persist_directory=PERSIST_DIR)
    print("✅ 向量库构建完成！")
    return vectordb


# ================= 智能加载 =================
def load_vector_db():
    if os.path.exists(PERSIST_DIR) and not REBUILD_FORCE:
        print("=" * 50)
        print("✅ 检测到已有向量库，直接加载！")
        print("=" * 50)
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        return Chroma(persist_directory=PERSIST_DIR, embedding_function=embeddings)
    else:
        if os.path.exists(PERSIST_DIR):
            shutil.rmtree(PERSIST_DIR)
        return build_vector_db()


# ================= 检索测试（无过滤、真返回TOP10） =================
def test_rag():
    vectordb = load_vector_db()
    print("\n" + "=" * 50)
    print("🔍 苏大政策 RAG 检索")
    print("=" * 50)

    query = "奖学金评选方法是什么？"
    print(f"❓ 问题：{query}")
    print("-" * 50)

    # 1. 向量库直接返回 TOP10 条结果（无任何过滤）
    raw_docs = vectordb.similarity_search(query, k=TOP_K)

    # 2. 仅做【基础去重】，去掉完全重复的内容
    seen = set()
    final_docs = []
    for doc in raw_docs:
        key = doc.page_content[:150]
        if key not in seen:
            seen.add(key)
            final_docs.append(doc)

    # 3. 展示所有结果（最多10条）
    for i, doc in enumerate(final_docs):
        print(f"✅ 结果 {i + 1}")
        print(f"📄 来源：{doc.metadata['source']}")
        print(f"📝 内容：\n{doc.page_content}\n{'-' * 50}")


if __name__ == "__main__":
    test_rag()
