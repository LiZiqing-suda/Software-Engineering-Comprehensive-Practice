import os
# 【关键修改1】设置环境变量，使用 HuggingFace 国内镜像，解决网络报错
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

# ================= 配置区域 =================
INPUT_DIR = "./RAG提取结果_高精度"
PERSIST_DIR = "./vector_db_suda"
# 仍然使用这个中文模型，但会通过镜像下载
EMBEDDING_MODEL_NAME = "shibing624/text2vec-base-chinese" 

def build_vector_db():
    print(f"正在通过镜像加载 Embedding 模型: {EMBEDDING_MODEL_NAME} ...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

    documents = []
    
    if not os.path.exists(INPUT_DIR):
        print(f"错误：找不到目录 {INPUT_DIR}，请检查路径。")
        return

    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".md"):
            file_path = os.path.join(INPUT_DIR, filename)
            print(f"读取文件: {filename}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            augmented_content = f"[文件名称：{filename}]\n{content}"
            doc = Document(
                page_content=augmented_content,
                metadata={"source": filename}
            )
            documents.append(doc)

    if not documents:
        print("目录下没有找到 Markdown 文件。")
        return

    # 切分文本
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""]
    )
    
    split_docs = text_splitter.split_documents(documents)
    print(f"文本切分完成，共 {len(split_docs)} 块。")

    # 构建向量库
    print("正在向量化...")
    vectordb = Chroma.from_documents(
        documents=split_docs,
        embedding=embeddings,
        persist_directory=PERSIST_DIR
    )
    
    # 【关键修改2】删除了 vectordb.persist()，新版 Chroma 会自动保存
    print(f"成功！向量库已自动保存至: {PERSIST_DIR}")

if __name__ == "__main__":
    build_vector_db()