import os
import base64
import io
import requests
import fitz
from PIL import Image
from docx import Document
import win32com.client

API_KEY = "API_KEY"
MODEL = "doubao-1-5-vision-pro-32k-250115"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

INPUT_FOLDER = "./RAG政策文件"
OUTPUT_FOLDER = "./RAG提取结果_高精度"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def doubao_ocr_image(pil_image):
    buffered = io.BytesIO()
    pil_image.convert("RGB").save(buffered, format="JPEG", quality=95)
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

    image_url = f"data:image/jpeg;base64,{base64_data}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    },
                    {
                        "type": "text",
                        "text": "高精度提取图片所有文字，完整输出，不改字不漏字，文档内容是苏州大学的政策或者通知文件，包含教务、学工等方面，结合这个背景进行提取，不要提取错字了。比如说䇹政基金这种名词需要慎重处理。"
                    }
                ]
            }
        ],
        "temperature": 0.01,
        "max_tokens": 8000
    }

    try:
        response = requests.post(BASE_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"错误：{str(e)}"


def extract_pdf(file_path):
    doc = fitz.open(file_path)
    full_text = ""
    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        print(f"处理第 {page_num + 1} 页...")
        page_text = doubao_ocr_image(img)
        full_text += f"--- 第 {page_num + 1} 页 ---\n{page_text}\n\n"
    return full_text


def extract_doc(file_path):
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(os.path.abspath(file_path))
        text = doc.Content.Text
        doc.Close()
        word.Quit()
        return text
    except:
        return "DOC提取失败"


def extract_docx(file_path):
    try:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except:
        return "DOCX提取失败"


if __name__ == "__main__":
    for filename in os.listdir(INPUT_FOLDER):
        fp = os.path.join(INPUT_FOLDER, filename)
        if not os.path.isfile(fp): continue

        base = os.path.splitext(filename)[0]
        out_path = os.path.join(OUTPUT_FOLDER, f"{base}.md")

        if os.path.exists(out_path):
            print(f"\n⏭️  已处理，跳过：{filename}")
            continue

        print(f"\n处理：{filename}")
        content = ""
        if filename.lower().endswith(".pdf"):
            content = extract_pdf(fp)
        elif filename.lower().endswith(".docx"):
            content = extract_docx(fp)
        elif filename.lower().endswith(".doc"):
            content = extract_doc(fp)
        else:
            continue

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 保存成功：{out_path}")

    print("\n🎉 全部完成！")