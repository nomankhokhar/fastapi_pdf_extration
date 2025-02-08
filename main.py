from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import fitz  # PyMuPDF for PDF handling
from fastapi.middleware.cors import CORSMiddleware
import requests
import io
import os
import concurrent.futures
import json
from pdfminer.high_level import extract_text
from paddleocr import PaddleOCR
from pydantic import BaseModel
import time
from PIL import Image

app = FastAPI()
ocr = PaddleOCR()



# Define request model
class PDFRequest(BaseModel):
    pdf_url: str

# Enable CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

def is_valid_pdf(url):
    try:
        response = requests.head(url, allow_redirects=True)
        return response.headers.get('Content-Type', '').lower() == 'application/pdf'
    except requests.exceptions.RequestException:
        return False

def download_chunk(start_byte, end_byte, url, download_path):
    headers = {'Range': f"bytes={start_byte}-{end_byte}"}
    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        with open(download_path, 'r+b') as f:
            f.seek(start_byte)
            f.write(response.content)
    except requests.exceptions.RequestException:
        pass

def download_pdf(url, download_path):
    try:
        session = requests.Session()
        response = session.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers['Content-Length'])
        with open(download_path, 'wb') as pdf_file:
            pdf_file.truncate(total_size)
        chunk_size = 1024 * 1024
        futures = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for start_byte in range(0, total_size, chunk_size):
                end_byte = min(start_byte + chunk_size - 1, total_size - 1)
                futures.append(executor.submit(download_chunk, start_byte, end_byte, url, download_path))
            concurrent.futures.wait(futures)
        session.close()
        return True
    except requests.exceptions.RequestException:
        return False

def extract_text_with_pdfminer(pdf_path):
    try:
        text = extract_text(pdf_path)
        return text if text.strip() else None
    except Exception:
        return None

def process_page_with_ocr(page_num, page, extracted_data):
    pix = page.get_pixmap()
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    result = ocr.ocr(img_byte_arr.getvalue(), cls=True)
    page_text = []
    for line in result:
        for word in line:
            text, bbox = word[1][0], word[0]
            page_text.append({"text": text, "bbox": bbox})
    extracted_data.append({"page": page_num + 1, "content": page_text})

def ocr_pdf(pdf_path):
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if file_size_mb > 50:
        return None
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    if num_pages > 2000:
        return None
    extracted_data = []
    for page_num, page in enumerate(doc, start=1):
        words = page.get_text("words")
        words.sort(key=lambda w: (w[1], w[0]))
        page_data = {"page": page_num, "words": []}
        for word in words:
            text, x0, y0, x1, y1 = word[4], word[0], word[1], word[2], word[3]
            page_data["words"].append({"text": text + " ", "bbox": [x0, y0, x1, y1]})
        if not page_data["words"]:
            process_page_with_ocr(page_num, page, extracted_data)
        else:
            extracted_data.append(page_data)
    doc.close()
    return extracted_data

def process_pdf_from_url(pdf_url):
    if is_valid_pdf(pdf_url):
        download_path = "downloaded.pdf"
        if download_pdf(pdf_url, download_path):
            return ocr_pdf(download_path)
    return None

@app.post("/extract")
async def extract_text_from_pdf(request: PDFRequest):
    text_data = process_pdf_from_url(request.pdf_url)
    if text_data is None:
        raise HTTPException(status_code=400, detail="Failed to process PDF.")
    return {"text": text_data}