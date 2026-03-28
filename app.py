import os
import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from PIL import Image
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas

# from reportlab.lib.pagesizes import letter
import traceback
import math
import subprocess
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.ns import qn
from reportlab.lib.pagesizes import letter, A4, landscape, portrait
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    Image as RLImage,
    KeepTogether,
    Preformatted,
    Frame,
    PageTemplate,
    BaseDocTemplate,
)
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from PIL import Image as PILImage
import tempfile
from pathlib import Path
from zipfile import ZipFile
import shutil

# ==================== Flask App Configuration ====================

app = Flask(__name__)
CORS(app)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(PROJECT_ROOT, "uploads")
app.config["OUTPUT_FOLDER"] = os.path.join(PROJECT_ROOT, "outputs")
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "png", "jpg", "jpeg"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["OUTPUT_FOLDER"], exist_ok=True)

app.static_folder = PROJECT_ROOT
app.static_url_path = ""

print(f"\n{'='*80}")
print("PDF TOOLKIT - Flask Backend (All 13 Tools)")
print(f"{'='*80}")
print(f"[INFO] Project Root: {PROJECT_ROOT}")
print(f"[INFO] Upload Folder: {app.config['UPLOAD_FOLDER']}")
print(f"[INFO] Output Folder: {app.config['OUTPUT_FOLDER']}")
print(f"[INFO] Max File Size: 50MB")
print(f"{'='*80}\n")

# ==================== HELPER FUNCTIONS ====================


def allowed_file(filename):
    """Check if file extension is allowed"""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def get_file_extension(filename):
    """Get file extension"""
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def image_to_pdf_buffer(image_path):
    """Convert image to PDF buffer"""
    try:
        img = Image.open(image_path)

        if img.mode == "RGBA":
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3])
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")

        pdf_buffer = BytesIO()
        img.save(pdf_buffer, format="PDF")
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    except Exception as e:
        raise Exception(f"Failed to convert image: {str(e)}")


def merge_pdfs(pdf_buffers):
    """Merge multiple PDF buffers into one"""
    try:
        pdf_merger = PyPDF2.PdfMerger()

        for pdf_buffer in pdf_buffers:
            pdf_reader = PdfReader(BytesIO(pdf_buffer))
            pdf_merger.append(pdf_reader)

        output_buffer = BytesIO()
        pdf_merger.write(output_buffer)
        pdf_merger.close()
        output_buffer.seek(0)
        return output_buffer.getvalue()
    except Exception as e:
        raise Exception(f"PDF merge failed: {str(e)}")


def parse_page_ranges(range_string, total_pages):
    """Parse page ranges and return list of page numbers"""
    try:
        pages = []
        ranges = [r.strip() for r in range_string.split(",")]

        for r in ranges:
            if "-" in r:
                parts = r.split("-")
                start = int(parts[0].strip())
                end_str = parts[1].strip()

                if end_str.upper() == "END":
                    end = total_pages
                else:
                    end = int(end_str)

                if start < 1 or end > total_pages or start > end:
                    raise ValueError(f"Invalid range: {start}-{end}")

                for page in range(start - 1, end):
                    if page not in pages:
                        pages.append(page)
            else:
                page_num = int(r.strip())
                if page_num < 1 or page_num > total_pages:
                    raise ValueError(f"Invalid page number: {page_num}")
                if page_num - 1 not in pages:
                    pages.append(page_num - 1)

        return sorted(pages)
    except Exception as e:
        raise Exception(f"Failed to parse page ranges: {str(e)}")


def split_pdf_by_ranges(pdf_buffer, page_ranges):
    """Split PDF by specific page ranges"""
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        total_pages = len(pdf_reader.pages)

        pages = parse_page_ranges(page_ranges, total_pages)

        if not pages:
            raise Exception("No valid pages selected")

        pdf_writer = PdfWriter()
        for page_num in pages:
            pdf_writer.add_page(pdf_reader.pages[page_num])

        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return [output_buffer.getvalue()]
    except Exception as e:
        raise Exception(f"Failed to split PDF: {str(e)}")


def split_pdf_by_interval(pdf_buffer, interval):
    """Split PDF by fixed interval"""
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        total_pages = len(pdf_reader.pages)
        interval = int(interval)

        if interval < 1 or interval > total_pages:
            raise ValueError(f"Invalid interval: {interval}")

        pdf_chunks = []
        for i in range(0, total_pages, interval):
            pdf_writer = PdfWriter()
            end = min(i + interval, total_pages)

            for page_num in range(i, end):
                pdf_writer.add_page(pdf_reader.pages[page_num])

            output_buffer = BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            pdf_chunks.append(output_buffer.getvalue())

        return pdf_chunks
    except Exception as e:
        raise Exception(f"Failed to split PDF: {str(e)}")


def protect_pdf_with_password(pdf_buffer, password, encryption_level=128):
    """Encrypt PDF with password - PyPDF2 3.0.1 compatible"""
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()

        for page_num in range(len(pdf_reader.pages)):
            pdf_writer.add_page(pdf_reader.pages[page_num])

        pdf_writer.encrypt(
            user_password=password, owner_password=password, permissions_flag=-1
        )

        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()
    except Exception as e:
        raise Exception(f"Failed to protect PDF: {str(e)}")


def unlock_pdf_with_password(pdf_buffer, password):
    """Decrypt PDF with password"""
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))

        if pdf_reader.is_encrypted:
            if not pdf_reader.decrypt(password):
                raise Exception("Incorrect password or unable to decrypt")

        pdf_writer = PdfWriter()

        for page_num in range(len(pdf_reader.pages)):
            pdf_writer.add_page(pdf_reader.pages[page_num])

        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()
    except Exception as e:
        raise Exception(f"Failed to unlock PDF: {str(e)}")


def create_zip(pdf_buffers):
    """Create a zip file from multiple PDF buffers"""
    try:
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, pdf_buffer in enumerate(pdf_buffers, 1):
                filename = f"split_part_{i}.pdf"
                zip_file.writestr(filename, pdf_buffer)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    except Exception as e:
        raise Exception(f"Failed to create zip: {str(e)}")


def cleanup_file(filepath):
    """Delete file after processing"""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[INFO] Cleaned up: {filepath}")
    except Exception as e:
        print(f"[WARNING] Could not delete: {filepath}")


# ==================== STATIC FILE ROUTES ====================


@app.route("/", methods=["GET"])
def home():
    """Home route"""
    return app.send_static_file("index.html")


@app.route("/index.html", methods=["GET"])
def index():
    """Serve index.html"""
    return app.send_static_file("index.html")


@app.route("/tools/merge-pdf.html", methods=["GET"])
def merge_pdf_page():
    """Serve merge-pdf.html"""
    tools_path = os.path.join(PROJECT_ROOT, "tools", "merge-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


@app.route("/tools/split-pdf.html", methods=["GET"])
def split_pdf_page():
    """Serve split-pdf.html"""
    tools_path = os.path.join(PROJECT_ROOT, "tools", "split-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


@app.route("/tools/protect-pdf.html", methods=["GET"])
def protect_pdf_page():
    """Serve protect-pdf.html"""
    tools_path = os.path.join(PROJECT_ROOT, "tools", "protect-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


@app.route("/tools/unlock-pdf.html", methods=["GET"])
def unlock_pdf_page():
    """Serve unlock-pdf.html"""
    tools_path = os.path.join(PROJECT_ROOT, "tools", "unlock-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


@app.route("/auth/<path:filename>", methods=["GET"])
def serve_auth(filename):
    """Serve files from auth folder"""
    auth_path = os.path.join(PROJECT_ROOT, "auth", secure_filename(filename))
    if os.path.exists(auth_path):
        return send_file(auth_path)
    return jsonify({"error": "File not found"}), 404


@app.route("/style.css", methods=["GET"])
def serve_css():
    """Serve style.css"""
    css_path = os.path.join(PROJECT_ROOT, "style.css")
    if os.path.exists(css_path):
        return send_file(css_path, mimetype="text/css")
    return jsonify({"error": "File not found"}), 404


@app.route("/script.js", methods=["GET"])
def serve_js():
    """Serve script.js"""
    js_path = os.path.join(PROJECT_ROOT, "script.js")
    if os.path.exists(js_path):
        return send_file(js_path, mimetype="application/javascript")
    return jsonify({"error": "File not found"}), 404


# ==================== MERGE PDF API ====================


@app.route("/api/merge-pdf", methods=["POST"])
def merge_pdf_api():
    """Merge PDF files endpoint"""
    uploaded_files = []

    try:
        print("[API] /api/merge-pdf called")

        if "files[]" not in request.files:
            return jsonify({"success": False, "message": "No files uploaded"}), 400

        files = request.files.getlist("files[]")
        print(f"[INFO] Received {len(files)} files")

        if not files or len(files) == 0:
            return jsonify({"success": False, "message": "No files selected"}), 400

        output_name = request.form.get("outputName", "merged_document.pdf")
        if not output_name.endswith(".pdf"):
            output_name = secure_filename(output_name) + ".pdf"
        else:
            output_name = secure_filename(output_name)

        print(f"[INFO] Output name: {output_name}")

        pdf_buffers = []

        for uploaded_file in files:
            if not uploaded_file or uploaded_file.filename == "":
                continue

            print(f"[INFO] Processing: {uploaded_file.filename}")

            if not allowed_file(uploaded_file.filename):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Invalid file type: {uploaded_file.filename}",
                        }
                    ),
                    400,
                )

            filename = secure_filename(uploaded_file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

            try:
                uploaded_file.save(filepath)
                uploaded_files.append(filepath)
                print(f"[INFO] Saved: {filepath}")
            except Exception as e:
                print(f"[ERROR] Failed to save: {str(e)}")
                return (
                    jsonify(
                        {"success": False, "message": f"Failed to upload {filename}"}
                    ),
                    500,
                )

            try:
                file_ext = get_file_extension(filename).lower()

                if file_ext == "pdf":
                    with open(filepath, "rb") as f:
                        pdf_buffers.append(f.read())
                elif file_ext in ["png", "jpg", "jpeg"]:
                    pdf_buffer = image_to_pdf_buffer(filepath)
                    pdf_buffers.append(pdf_buffer)
                else:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": f"Unsupported file type: {file_ext}",
                            }
                        ),
                        400,
                    )

            except Exception as e:
                print(f"[ERROR] Processing error: {str(e)}")
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Error processing {filename}: {str(e)}",
                        }
                    ),
                    500,
                )

        if not pdf_buffers:
            return (
                jsonify({"success": False, "message": "No valid PDF files to merge"}),
                400,
            )

        print(f"[INFO] Merging {len(pdf_buffers)} PDFs")

        try:
            merged_pdf_buffer = merge_pdfs(pdf_buffers)
            print("[INFO] PDF merge completed")
        except Exception as e:
            print(f"[ERROR] Merge failed: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Merge failed: {str(e)}"}),
                500,
            )

        output_filename = f"{uuid.uuid4()}_{output_name}"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(merged_pdf_buffer)
            print(f"[INFO] Saved output: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return (
                jsonify(
                    {"success": False, "message": f"Failed to save output: {str(e)}"}
                ),
                500,
            )

        for filepath in uploaded_files:
            cleanup_file(filepath)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": output_name,
            "message": "PDF merge completed successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        for filepath in uploaded_files:
            cleanup_file(filepath)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        for filepath in uploaded_files:
            cleanup_file(filepath)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== SPLIT PDF API ====================


@app.route("/api/split-pdf", methods=["POST"])
def split_pdf_api():
    """Split PDF file endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/split-pdf called")

        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        if (
            not allowed_file(uploaded_file.filename)
            or get_file_extension(uploaded_file.filename) != "pdf"
        ):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        split_mode = request.form.get("splitMode", "range")
        page_ranges = request.form.get("pageRanges", "")
        split_interval = request.form.get("splitInterval", "1")

        print(f"[INFO] Split mode: {split_mode}")

        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        try:
            if split_mode == "range":
                if not page_ranges.strip():
                    return (
                        jsonify(
                            {"success": False, "message": "Please enter page ranges"}
                        ),
                        400,
                    )
                print(f"[INFO] Splitting by ranges: {page_ranges}")
                pdf_chunks = split_pdf_by_ranges(pdf_buffer, page_ranges)
            else:
                print(f"[INFO] Splitting by interval: {split_interval}")
                pdf_chunks = split_pdf_by_interval(pdf_buffer, split_interval)

            print(f"[INFO] Created {len(pdf_chunks)} PDF chunks")
        except Exception as e:
            print(f"[ERROR] Split failed: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Split failed: {str(e)}"}),
                500,
            )

        if len(pdf_chunks) > 1:
            try:
                zip_buffer = create_zip(pdf_chunks)
                output_filename = f"{uuid.uuid4()}_split.zip"
                output_filepath = os.path.join(
                    app.config["OUTPUT_FOLDER"], output_filename
                )

                with open(output_filepath, "wb") as f:
                    f.write(zip_buffer)

                print(f"[INFO] Saved zip: {output_filepath}")
                download_url = f"/api/download-zip/{output_filename}"
                filename_response = "split_document.zip"
            except Exception as e:
                print(f"[ERROR] Failed to create zip: {str(e)}")
                return (
                    jsonify(
                        {"success": False, "message": f"Failed to create zip: {str(e)}"}
                    ),
                    500,
                )
        else:
            output_filename = f"{uuid.uuid4()}_split.pdf"
            output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

            try:
                with open(output_filepath, "wb") as f:
                    f.write(pdf_chunks[0])

                print(f"[INFO] Saved PDF: {output_filepath}")
                download_url = f"/api/download-pdf/{output_filename}"
                filename_response = "split_document.pdf"
            except Exception as e:
                print(f"[ERROR] Failed to save: {str(e)}")
                return (
                    jsonify(
                        {"success": False, "message": f"Failed to save PDF: {str(e)}"}
                    ),
                    500,
                )

        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": download_url,
            "filename": filename_response,
            "message": "PDF split completed successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== PROTECT PDF API ====================


@app.route("/api/protect-pdf", methods=["POST"])
def protect_pdf_api():
    """Protect PDF with password endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/protect-pdf called")

        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        if (
            not allowed_file(uploaded_file.filename)
            or get_file_extension(uploaded_file.filename) != "pdf"
        ):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        password = request.form.get("password", "")
        encryption = request.form.get("encryption", "128")

        if not password:
            return jsonify({"success": False, "message": "Password is required"}), 400

        if len(password) < 6:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Password must be at least 6 characters",
                    }
                ),
                400,
            )

        print(f"[INFO] Encryption level: {encryption}-bit")

        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        try:
            encryption_level = int(encryption)
            protected_buffer = protect_pdf_with_password(
                pdf_buffer, password, encryption_level
            )
            print(f"[INFO] PDF protected with {encryption_level}-bit encryption")
        except Exception as e:
            print(f"[ERROR] Protection failed: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Protection failed: {str(e)}"}),
                500,
            )

        output_filename = f"{uuid.uuid4()}_protected.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(protected_buffer)
            print(f"[INFO] Saved: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": "protected_document.pdf",
            "message": "PDF protected successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== UNLOCK PDF API ====================


@app.route("/api/unlock-pdf", methods=["POST"])
def unlock_pdf_api():
    """Unlock PDF with password endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/unlock-pdf called")

        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        if (
            not allowed_file(uploaded_file.filename)
            or get_file_extension(uploaded_file.filename) != "pdf"
        ):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        password = request.form.get("password", "")

        if not password:
            return jsonify({"success": False, "message": "Password is required"}), 400

        print(f"[INFO] Attempting to decrypt PDF")

        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        try:
            unlocked_buffer = unlock_pdf_with_password(pdf_buffer, password)
            print(f"[INFO] PDF unlocked successfully")
        except Exception as e:
            print(f"[ERROR] Unlock failed: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Unlock failed: {str(e)}"}),
                500,
            )

        output_filename = f"{uuid.uuid4()}_unlocked.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(unlocked_buffer)
            print(f"[INFO] Saved: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": "unlocked_document.pdf",
            "message": "PDF unlocked successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== HELPER FUNCTIONS FOR IMAGE TO PDF ====================


def is_image_file(filename):
    """Check if file is an image"""
    image_extensions = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in image_extensions


def image_to_pdf_buffer(image_path):
    """Convert single image to PDF buffer"""
    try:
        img = Image.open(image_path)

        # Handle different image modes
        if img.mode == "RGBA":
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3])
            img = rgb_img
        elif img.mode == "P":
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        pdf_buffer = BytesIO()
        img.save(pdf_buffer, format="PDF", resolution=100.0)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    except Exception as e:
        raise Exception(f"Failed to convert image: {str(e)}")


def images_to_pdf_buffer(image_paths, page_size="A4", orientation="portrait"):
    """Convert multiple images to a single PDF with page size and orientation"""
    try:
        try:
            from reportlab.lib.pagesizes import A4, LETTER, LEGAL
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas

            # Define page sizes
            page_sizes = {"A4": A4, "Letter": LETTER, "Legal": LEGAL}

            page_dim = page_sizes.get(page_size, A4)

            # Swap dimensions for landscape
            if orientation == "landscape":
                page_dim = (page_dim[1], page_dim[0])

            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=page_dim)

            page_width, page_height = page_dim
            margin = 0.5 * inch

            for image_path in image_paths:
                img = Image.open(image_path)

                # Convert to RGB if necessary
                if img.mode == "RGBA":
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])
                    img = rgb_img
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                img_width, img_height = img.size

                # Calculate scaling to fit page with margins
                available_width = page_width - (2 * margin)
                available_height = page_height - (2 * margin)

                width_ratio = available_width / img_width
                height_ratio = available_height / img_height
                ratio = min(width_ratio, height_ratio)

                new_width = img_width * ratio
                new_height = img_height * ratio

                # Center the image
                x = (page_width - new_width) / 2
                y = (page_height - new_height) / 2

                # Save temporary image
                temp_img_path = image_path + "_temp.jpg"
                img.save(temp_img_path, "JPEG", quality=95)

                # Draw image on canvas
                c.drawImage(temp_img_path, x, y, width=new_width, height=new_height)
                c.showPage()

                # Clean up temp file
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)

            c.save()
            pdf_buffer.seek(0)
            return pdf_buffer.getvalue()

        except ImportError:
            # Fallback method without reportlab - simpler conversion
            print("[INFO] reportlab not available, using simple conversion")
            pdf_buffers = []
            for image_path in image_paths:
                pdf_buffers.append(image_to_pdf_buffer(image_path))

            # Merge all PDFs
            pdf_merger = PyPDF2.PdfMerger()
            for pdf_buffer in pdf_buffers:
                pdf_reader = PdfReader(BytesIO(pdf_buffer))
                pdf_merger.append(pdf_reader)

            output_buffer = BytesIO()
            pdf_merger.write(output_buffer)
            pdf_merger.close()
            output_buffer.seek(0)
            return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to convert images to PDF: {str(e)}")


def cleanup_file(filepath):
    """Delete file after processing"""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[INFO] Cleaned up: {filepath}")
    except Exception as e:
        print(f"[WARNING] Could not delete: {filepath}")


# ==================== IMAGE TO PDF API ENDPOINT ====================


@app.route("/api/image-to-pdf", methods=["POST"])
def image_to_pdf_api():
    """Convert images to PDF endpoint"""
    uploaded_files = []

    try:
        print("[API] /api/image-to-pdf called")

        # Debug: Print all form data and files
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for files with different possible field names
        files = None
        if "images[]" in request.files:
            files = request.files.getlist("images[]")
            print(f"[INFO] Found images[] with {len(files)} files")
        elif "files[]" in request.files:
            files = request.files.getlist("files[]")
            print(f"[INFO] Found files[] with {len(files)} files")
        elif "files" in request.files:
            files = request.files.getlist("files")
            print(f"[INFO] Found files with {len(files)} files")
        elif "images" in request.files:
            files = request.files.getlist("images")
            print(f"[INFO] Found images with {len(files)} files")
        elif "file" in request.files:
            files = [request.files["file"]]
            print(f"[INFO] Found single file")
        else:
            print(f"[ERROR] No files found in request")
            print(f"[ERROR] Available keys: {list(request.files.keys())}")
            return jsonify({"success": False, "message": "No files uploaded"}), 400

        if not files or len(files) == 0:
            return jsonify({"success": False, "message": "No files selected"}), 400

        # Filter out empty file entries
        files = [f for f in files if f and f.filename != ""]

        if len(files) == 0:
            return (
                jsonify({"success": False, "message": "No valid files selected"}),
                400,
            )

        print(f"[INFO] Processing {len(files)} files")

        # Get conversion options
        output_name = request.form.get("outputName", "converted_document.pdf")
        page_size = request.form.get("pageSize", "A4")
        orientation = request.form.get("orientation", "portrait")

        if not output_name.endswith(".pdf"):
            output_name = secure_filename(output_name) + ".pdf"
        else:
            output_name = secure_filename(output_name)

        print(f"[INFO] Output name: {output_name}")
        print(f"[INFO] Page size: {page_size}, Orientation: {orientation}")

        image_paths = []

        # Save all uploaded images
        for uploaded_file in files:
            if not uploaded_file or uploaded_file.filename == "":
                continue

            print(f"[INFO] Processing: {uploaded_file.filename}")

            if not is_image_file(uploaded_file.filename):
                # Cleanup already uploaded files
                for filepath in uploaded_files:
                    cleanup_file(filepath)
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Only image files allowed: {uploaded_file.filename}",
                        }
                    ),
                    400,
                )

            filename = secure_filename(uploaded_file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

            try:
                uploaded_file.save(filepath)
                uploaded_files.append(filepath)
                image_paths.append(filepath)
                print(f"[INFO] Saved: {filepath}")
            except Exception as e:
                print(f"[ERROR] Failed to save: {str(e)}")
                # Cleanup already uploaded files
                for fp in uploaded_files:
                    cleanup_file(fp)
                return (
                    jsonify(
                        {"success": False, "message": f"Failed to upload {filename}"}
                    ),
                    500,
                )

        if not image_paths:
            return (
                jsonify({"success": False, "message": "No valid image files uploaded"}),
                400,
            )

        print(f"[INFO] Converting {len(image_paths)} images to PDF")

        try:
            # Convert images to PDF with specified settings
            pdf_buffer = images_to_pdf_buffer(image_paths, page_size, orientation)
            print("[INFO] Image to PDF conversion completed")
        except Exception as e:
            print(f"[ERROR] Conversion failed: {str(e)}")
            print(traceback.format_exc())
            # Cleanup uploaded files
            for filepath in uploaded_files:
                cleanup_file(filepath)
            return (
                jsonify({"success": False, "message": f"Conversion failed: {str(e)}"}),
                500,
            )

        # Save output PDF
        output_filename = f"{uuid.uuid4()}_{output_name}"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(pdf_buffer)
            print(f"[INFO] Saved output: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            # Cleanup uploaded files
            for filepath in uploaded_files:
                cleanup_file(filepath)
            return (
                jsonify(
                    {"success": False, "message": f"Failed to save output: {str(e)}"}
                ),
                500,
            )

        # Cleanup uploaded files
        for filepath in uploaded_files:
            cleanup_file(filepath)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": output_name,
            "message": "Images converted to PDF successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        for filepath in uploaded_files:
            cleanup_file(filepath)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        for filepath in uploaded_files:
            cleanup_file(filepath)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR IMAGE TO PDF PAGE ====================


@app.route("/tools/image-to-pdf.html", methods=["GET"])
def image_to_pdf_page():
    """Serve image-to-pdf.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "image-to-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTION FOR PDF TO JPG ====================


def pdf_to_images(pdf_path, quality=85):
    """Convert PDF pages to JPG images"""
    try:
        images = []
        pdf_document = fitz.open(pdf_path)

        print(f"[INFO] PDF has {pdf_document.page_count} pages")

        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]

            # Set zoom for quality (higher = better quality)
            zoom = 2 if quality >= 85 else 1.5 if quality >= 60 else 1
            mat = fitz.Matrix(zoom, zoom)

            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat)

            # Convert pixmap to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(BytesIO(img_data))

            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Save as JPG with specified quality
            img_buffer = BytesIO()
            img.save(img_buffer, format="JPEG", quality=int(quality), optimize=True)
            img_buffer.seek(0)

            images.append(
                {"data": img_buffer.getvalue(), "filename": f"page_{page_num + 1}.jpg"}
            )

            print(f"[INFO] Converted page {page_num + 1}/{pdf_document.page_count}")

        pdf_document.close()
        return images

    except Exception as e:
        raise Exception(f"Failed to convert PDF to images: {str(e)}")


def create_images_zip(images):
    """Create ZIP file from image list"""
    try:
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for img in images:
                zip_file.writestr(img["filename"], img["data"])

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to create ZIP: {str(e)}")


# ==================== PDF TO JPG API ENDPOINT ====================


@app.route("/api/pdf-to-jpg", methods=["POST"])
def pdf_to_jpg_api():
    """Convert PDF to JPG images endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/pdf-to-jpg called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get quality parameter
        quality = int(request.form.get("quality", "85"))
        print(f"[INFO] Quality: {quality}%")

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Convert PDF to images
        try:
            print(f"[INFO] Starting PDF to JPG conversion...")
            images = pdf_to_images(uploaded_file_path, quality)
            print(f"[INFO] Converted {len(images)} pages to JPG")
        except Exception as e:
            print(f"[ERROR] Conversion failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Conversion failed: {str(e)}"}),
                500,
            )

        # Create ZIP file
        try:
            print(f"[INFO] Creating ZIP file...")
            zip_buffer = create_images_zip(images)

            output_filename = f"{uuid.uuid4()}_images.zip"
            output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

            with open(output_filepath, "wb") as f:
                f.write(zip_buffer)

            print(f"[INFO] Saved ZIP: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to create ZIP: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify(
                    {"success": False, "message": f"Failed to create ZIP: {str(e)}"}
                ),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-zip/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_images.zip",
            "message": f"PDF converted to {len(images)} JPG images successfully",
            "pageCount": len(images),
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR PDF TO JPG PAGE ====================


@app.route("/tools/pdf-to-jpg.html", methods=["GET"])
def pdf_to_jpg_page():
    """Serve pdf-to-jpg.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "pdf-to-jpg.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTION FOR PDF ROTATION ====================


def parse_page_ranges_for_rotation(range_string, total_pages):
    """Parse page ranges and return list of page numbers (0-indexed)"""
    try:
        pages = set()
        ranges = [r.strip() for r in range_string.split(",")]

        for r in ranges:
            if "-" in r:
                parts = r.split("-")
                start = int(parts[0].strip())
                end_str = parts[1].strip()

                if end_str.upper() == "END":
                    end = total_pages
                else:
                    end = int(end_str)

                if start < 1 or end > total_pages or start > end:
                    raise ValueError(f"Invalid range: {start}-{end}")

                for page in range(start - 1, end):
                    pages.add(page)
            else:
                page_num = int(r.strip())
                if page_num < 1 or page_num > total_pages:
                    raise ValueError(f"Invalid page number: {page_num}")
                pages.add(page_num - 1)

        return sorted(list(pages))
    except Exception as e:
        raise Exception(f"Failed to parse page ranges: {str(e)}")


def rotate_pdf_pages(pdf_buffer, rotation_angle, apply_to="all", page_range=""):
    """Rotate PDF pages by specified angle"""
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()
        total_pages = len(pdf_reader.pages)

        print(f"[INFO] PDF has {total_pages} pages")
        print(f"[INFO] Rotation: {rotation_angle}°, Apply to: {apply_to}")

        # Determine which pages to rotate
        if apply_to == "all":
            pages_to_rotate = set(range(total_pages))
        else:
            pages_to_rotate = set(
                parse_page_ranges_for_rotation(page_range, total_pages)
            )

        print(f"[INFO] Rotating {len(pages_to_rotate)} pages")

        # Process all pages
        for page_num in range(total_pages):
            page = pdf_reader.pages[page_num]

            if page_num in pages_to_rotate:
                # Rotate the page
                page.rotate(int(rotation_angle))
                print(f"[INFO] Rotated page {page_num + 1} by {rotation_angle}°")

            pdf_writer.add_page(page)

        # Write to buffer
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to rotate PDF: {str(e)}")


# ==================== ROTATE PDF API ENDPOINT ====================


@app.route("/api/rotate-pdf", methods=["POST"])
def rotate_pdf_api():
    """Rotate PDF pages endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/rotate-pdf called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get rotation parameters
        rotation_angle = request.form.get("rotation", "90")
        apply_to = request.form.get("applyTo", "all")
        page_range = request.form.get("pageRange", "")

        print(f"[INFO] Rotation: {rotation_angle}°")
        print(f"[INFO] Apply to: {apply_to}")
        if apply_to == "selected":
            print(f"[INFO] Page range: {page_range}")

        # Validate rotation angle
        if rotation_angle not in ["90", "180", "270"]:
            return jsonify({"success": False, "message": "Invalid rotation angle"}), 400

        # Validate page range for selected pages
        if apply_to == "selected" and not page_range.strip():
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Page range required for selected pages",
                    }
                ),
                400,
            )

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Read PDF buffer
        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        # Rotate PDF
        try:
            print(f"[INFO] Starting PDF rotation...")
            rotated_buffer = rotate_pdf_pages(
                pdf_buffer, rotation_angle, apply_to, page_range
            )
            print(f"[INFO] PDF rotation completed")
        except Exception as e:
            print(f"[ERROR] Rotation failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Rotation failed: {str(e)}"}),
                500,
            )

        # Save rotated PDF
        output_filename = f"{uuid.uuid4()}_rotated.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(rotated_buffer)
            print(f"[INFO] Saved rotated PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_rotated.pdf",
            "message": f"PDF rotated {rotation_angle}° successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR ROTATE PDF PAGE ====================


@app.route("/tools/rotate-pdf.html", methods=["GET"])
def rotate_pdf_page():
    """Serve rotate-pdf.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "rotate-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTION FOR PDF COMPRESSION ====================


def compress_pdf(pdf_buffer, compression_level="medium"):
    """
    Compress PDF by removing unnecessary data and optimizing content streams

    Compression levels:
    - low: Minimal compression, high quality
    - medium: Balanced compression
    - high: Maximum compression, lower quality
    """
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()

        total_pages = len(pdf_reader.pages)
        print(f"[INFO] PDF has {total_pages} pages")
        print(f"[INFO] Compression level: {compression_level}")

        # Process each page
        for page_num in range(total_pages):
            page = pdf_reader.pages[page_num]

            # Compress content streams if method exists
            try:
                if hasattr(page, "compress_content_streams"):
                    page.compress_content_streams()
            except Exception as e:
                print(f"[WARNING] Could not compress page {page_num + 1}: {str(e)}")

            pdf_writer.add_page(page)
            print(f"[INFO] Processed page {page_num + 1}/{total_pages}")

        # Apply additional compression for high level
        if compression_level == "high":
            # Compress all pages again for maximum reduction
            for page in pdf_writer.pages:
                try:
                    if hasattr(page, "compress_content_streams"):
                        page.compress_content_streams()
                except:
                    pass

        # Optimize metadata
        try:
            pdf_writer.add_metadata(
                {"/Producer": "PDF Toolkit", "/Creator": "PDF Toolkit"}
            )
        except:
            pass

        # Write compressed PDF
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to compress PDF: {str(e)}")


def calculate_reduction(original_size, compressed_size):
    """Calculate compression reduction percentage"""
    if original_size == 0:
        return 0
    reduction = ((original_size - compressed_size) / original_size) * 100
    return round(reduction, 2)


# ==================== COMPRESS PDF API ENDPOINT ====================


@app.route("/api/compress-pdf", methods=["POST"])
def compress_pdf_api():
    """Compress PDF endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/compress-pdf called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get compression level
        compression_level = request.form.get("compressionLevel", "medium")

        if compression_level not in ["low", "medium", "high"]:
            compression_level = "medium"

        print(f"[INFO] Compression level: {compression_level}")

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Get original file size
        original_size = os.path.getsize(uploaded_file_path)
        print(f"[INFO] Original size: {original_size / (1024 * 1024):.2f} MB")

        # Read PDF buffer
        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        # Compress PDF
        try:
            print(f"[INFO] Starting PDF compression...")
            compressed_buffer = compress_pdf(pdf_buffer, compression_level)
            compressed_size = len(compressed_buffer)
            print(f"[INFO] Compressed size: {compressed_size / (1024 * 1024):.2f} MB")
            print(f"[INFO] PDF compression completed")
        except Exception as e:
            print(f"[ERROR] Compression failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Compression failed: {str(e)}"}),
                500,
            )

        # Calculate reduction percentage
        reduction_percent = calculate_reduction(original_size, compressed_size)
        print(f"[INFO] Size reduction: {reduction_percent}%")

        # If compression increased size or no reduction, use original
        if compressed_size >= original_size:
            print(
                f"[WARNING] Compression increased or maintained size, using original file"
            )
            compressed_buffer = pdf_buffer
            compressed_size = original_size
            reduction_percent = 0

        # Save compressed PDF
        output_filename = f"{uuid.uuid4()}_compressed.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(compressed_buffer)
            print(f"[INFO] Saved compressed PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        # Prepare response message
        if reduction_percent > 0:
            message = f"PDF compressed successfully by {reduction_percent}%"
        else:
            message = "PDF optimized (file was already compressed)"

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_compressed.pdf",
            "message": message,
            "originalSize": f"{original_size / (1024 * 1024):.2f} MB",
            "compressedSize": f"{compressed_size / (1024 * 1024):.2f} MB",
            "reductionPercent": reduction_percent,
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR COMPRESS PDF PAGE ====================


@app.route("/tools/compress-pdf.html", methods=["GET"])
def compress_pdf_page():
    """Serve compress-pdf.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "compress-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTION FOR ADDING PAGE NUMBERS ====================


def add_page_numbers_to_pdf(
    pdf_buffer, position="bottom-right", font_size=12, start_page=1
):
    """
    Add page numbers to PDF

    Args:
        pdf_buffer: PDF file bytes
        position: Position of page number (bottom-right, bottom-center, bottom-left, top-right, top-center, top-left)
        font_size: Font size in points
        start_page: Page number to start from (1-indexed)
    """
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()
        total_pages = len(pdf_reader.pages)

        print(f"[INFO] PDF has {total_pages} pages")
        print(
            f"[INFO] Position: {position}, Font size: {font_size}pt, Start from page: {start_page}"
        )

        for page_num in range(total_pages):
            page = pdf_reader.pages[page_num]

            # Get page dimensions
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            # Create a new PDF with the page number
            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            # Calculate page number to display
            display_number = page_num + start_page
            page_number_text = str(display_number)

            # Set font
            can.setFont("Helvetica", font_size)

            # Calculate position coordinates
            margin = 30  # Points from edge
            text_width = can.stringWidth(page_number_text, "Helvetica", font_size)

            if position == "bottom-right":
                x = page_width - text_width - margin
                y = margin
            elif position == "bottom-center":
                x = (page_width - text_width) / 2
                y = margin
            elif position == "bottom-left":
                x = margin
                y = margin
            elif position == "top-right":
                x = page_width - text_width - margin
                y = page_height - margin - font_size
            elif position == "top-center":
                x = (page_width - text_width) / 2
                y = page_height - margin - font_size
            elif position == "top-left":
                x = margin
                y = page_height - margin - font_size
            else:
                # Default to bottom-right
                x = page_width - text_width - margin
                y = margin

            # Draw the page number
            can.drawString(x, y, page_number_text)
            can.save()

            # Move to the beginning of the BytesIO buffer
            packet.seek(0)

            # Read the page number PDF
            number_pdf = PdfReader(packet)
            number_page = number_pdf.pages[0]

            # Merge the page number onto the original page
            page.merge_page(number_page)

            # Add the modified page to the writer
            pdf_writer.add_page(page)

            print(f"[INFO] Added number to page {page_num + 1}/{total_pages}")

        # Write to output buffer
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to add page numbers: {str(e)}")


# ==================== ADD PAGE NUMBERS API ENDPOINT ====================


@app.route("/api/add-page-numbers", methods=["POST"])
def add_page_numbers_api():
    """Add page numbers to PDF endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/add-page-numbers called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get parameters
        position = request.form.get("position", "bottom-right")
        font_size = int(request.form.get("fontSize", "12"))
        start_page = int(request.form.get("startPage", "1"))

        # Validate parameters
        valid_positions = [
            "bottom-right",
            "bottom-center",
            "bottom-left",
            "top-right",
            "top-center",
            "top-left",
        ]
        if position not in valid_positions:
            position = "bottom-right"

        if font_size < 8 or font_size > 48:
            font_size = 12

        if start_page < 1:
            start_page = 1

        print(f"[INFO] Position: {position}")
        print(f"[INFO] Font size: {font_size}pt")
        print(f"[INFO] Start from page: {start_page}")

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Read PDF buffer
        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        # Add page numbers
        try:
            print(f"[INFO] Starting to add page numbers...")
            numbered_buffer = add_page_numbers_to_pdf(
                pdf_buffer, position, font_size, start_page
            )
            print(f"[INFO] Page numbers added successfully")
        except Exception as e:
            print(f"[ERROR] Adding page numbers failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Failed to add page numbers: {str(e)}",
                    }
                ),
                500,
            )

        # Save numbered PDF
        output_filename = f"{uuid.uuid4()}_numbered.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(numbered_buffer)
            print(f"[INFO] Saved numbered PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_numbered.pdf",
            "message": "Page numbers added successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR ADD PAGE NUMBERS PAGE ====================


@app.route("/tools/add-page-numbers.html", methods=["GET"])
def add_page_numbers_page():
    """Serve add-page-numbers.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "add-page-numbers.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTION FOR ADDING WATERMARK ====================


def add_watermark_to_pdf(
    pdf_buffer, watermark_text="DRAFT", position="diagonal", opacity=0.5, font_size=60
):
    """
    Add text watermark to PDF

    Args:
        pdf_buffer: PDF file bytes
        watermark_text: Text to display as watermark
        position: Position (diagonal, center, top-center, bottom-center)
        opacity: Transparency (0.1 to 1.0)
        font_size: Font size in points
    """
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()
        total_pages = len(pdf_reader.pages)

        print(f"[INFO] PDF has {total_pages} pages")
        print(
            f"[INFO] Watermark: '{watermark_text}', Position: {position}, Opacity: {opacity}"
        )

        for page_num in range(total_pages):
            page = pdf_reader.pages[page_num]

            # Get page dimensions
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            # Create watermark
            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            # Set font and opacity
            can.setFont("Helvetica-Bold", font_size)
            can.setFillColorRGB(0.5, 0.5, 0.5, alpha=opacity)

            # Calculate position
            text_width = can.stringWidth(watermark_text, "Helvetica-Bold", font_size)

            if position == "diagonal":
                # Diagonal watermark (most common)
                # Calculate center and rotate
                x = page_width / 2
                y = page_height / 2

                # Rotate 45 degrees
                can.saveState()
                can.translate(x, y)
                can.rotate(45)
                can.drawCentredString(0, 0, watermark_text)
                can.restoreState()

            elif position == "center":
                # Center watermark
                x = page_width / 2
                y = page_height / 2
                can.drawCentredString(x, y, watermark_text)

            elif position == "top-center":
                # Top center
                x = page_width / 2
                y = page_height - 100
                can.drawCentredString(x, y, watermark_text)

            elif position == "bottom-center":
                # Bottom center
                x = page_width / 2
                y = 100
                can.drawCentredString(x, y, watermark_text)
            else:
                # Default to diagonal
                x = page_width / 2
                y = page_height / 2
                can.saveState()
                can.translate(x, y)
                can.rotate(45)
                can.drawCentredString(0, 0, watermark_text)
                can.restoreState()

            can.save()
            packet.seek(0)

            # Merge watermark with page
            watermark_pdf = PdfReader(packet)
            watermark_page = watermark_pdf.pages[0]
            page.merge_page(watermark_page)

            pdf_writer.add_page(page)
            print(f"[INFO] Added watermark to page {page_num + 1}/{total_pages}")

        # Write output
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to add watermark: {str(e)}")


# ==================== ADD WATERMARK API ENDPOINT ====================


@app.route("/api/add-watermark", methods=["POST"])
def add_watermark_api():
    """Add watermark to PDF endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/add-watermark called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get parameters
        watermark_text = request.form.get("watermarkText", "DRAFT")
        position = request.form.get("position", "diagonal")
        opacity = float(request.form.get("opacity", "0.5"))
        font_size = int(request.form.get("fontSize", "60"))

        # Validate parameters
        valid_positions = ["diagonal", "center", "top-center", "bottom-center"]
        if position not in valid_positions:
            position = "diagonal"

        if opacity < 0.1 or opacity > 1.0:
            opacity = 0.5

        if font_size < 20 or font_size > 100:
            font_size = 60

        if not watermark_text or len(watermark_text) > 100:
            watermark_text = "DRAFT"

        print(f"[INFO] Watermark text: '{watermark_text}'")
        print(
            f"[INFO] Position: {position}, Opacity: {opacity}, Font size: {font_size}pt"
        )

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Read PDF buffer
        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        # Add watermark
        try:
            print(f"[INFO] Starting to add watermark...")
            watermarked_buffer = add_watermark_to_pdf(
                pdf_buffer, watermark_text, position, opacity, font_size
            )
            print(f"[INFO] Watermark added successfully")
        except Exception as e:
            print(f"[ERROR] Adding watermark failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify(
                    {"success": False, "message": f"Failed to add watermark: {str(e)}"}
                ),
                500,
            )

        # Save watermarked PDF
        output_filename = f"{uuid.uuid4()}_watermarked.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(watermarked_buffer)
            print(f"[INFO] Saved watermarked PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_watermarked.pdf",
            "message": f"Watermark '{watermark_text}' added successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR ADD WATERMARK PAGE ====================


@app.route("/tools/add-watermark.html", methods=["GET"])
def add_watermark_page():
    """Serve add-watermark.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "add-watermark.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTIONS FOR REMOVING PAGES ====================


def parse_page_numbers_to_remove(page_string, total_pages):
    """
    Parse page numbers string and return set of page indices to remove (0-indexed)

    Examples:
        "2, 5-7, 10" -> {1, 4, 5, 6, 9}
        "1-3" -> {0, 1, 2}
    """
    try:
        pages_to_remove = set()
        parts = [p.strip() for p in page_string.split(",")]

        for part in parts:
            if "-" in part:
                # Handle range (e.g., "5-7")
                range_parts = part.split("-")
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())

                if start < 1 or end > total_pages or start > end:
                    raise ValueError(f"Invalid range: {start}-{end}")

                # Add all pages in range (convert to 0-indexed)
                for page in range(start - 1, end):
                    pages_to_remove.add(page)
            else:
                # Handle single page
                page_num = int(part.strip())

                if page_num < 1 or page_num > total_pages:
                    raise ValueError(f"Invalid page number: {page_num}")

                # Convert to 0-indexed
                pages_to_remove.add(page_num - 1)

        return pages_to_remove

    except Exception as e:
        raise Exception(f"Failed to parse page numbers: {str(e)}")


def remove_pages_from_pdf(pdf_buffer, page_numbers_string):
    """
    Remove specified pages from PDF

    Args:
        pdf_buffer: PDF file bytes
        page_numbers_string: String like "2, 5-7, 10"

    Returns:
        PDF bytes with pages removed
    """
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        total_pages = len(pdf_reader.pages)

        print(f"[INFO] PDF has {total_pages} pages")
        print(f"[INFO] Pages to remove: {page_numbers_string}")

        # Parse which pages to remove
        pages_to_remove = parse_page_numbers_to_remove(page_numbers_string, total_pages)

        if not pages_to_remove:
            raise Exception("No valid pages specified for removal")

        if len(pages_to_remove) >= total_pages:
            raise Exception("Cannot remove all pages from PDF")

        print(
            f"[INFO] Removing {len(pages_to_remove)} pages: {sorted([p+1 for p in pages_to_remove])}"
        )

        # Create new PDF with remaining pages
        pdf_writer = PdfWriter()
        pages_kept = 0

        for page_num in range(total_pages):
            if page_num not in pages_to_remove:
                pdf_writer.add_page(pdf_reader.pages[page_num])
                pages_kept += 1
                print(f"[INFO] Kept page {page_num + 1}")

        print(
            f"[INFO] Final PDF will have {pages_kept} pages (removed {len(pages_to_remove)})"
        )

        # Write to buffer
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to remove pages: {str(e)}")


# ==================== REMOVE PAGES API ENDPOINT ====================


@app.route("/api/remove-pages", methods=["POST"])
def remove_pages_api():
    """Remove pages from PDF endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/remove-pages called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get page numbers to remove
        page_numbers = request.form.get("pageNumbers", "").strip()

        if not page_numbers:
            return (
                jsonify({"success": False, "message": "Page numbers are required"}),
                400,
            )

        print(f"[INFO] Pages to remove: {page_numbers}")

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Read PDF buffer
        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        # Remove pages
        try:
            print(f"[INFO] Starting page removal...")
            result_buffer = remove_pages_from_pdf(pdf_buffer, page_numbers)
            print(f"[INFO] Pages removed successfully")
        except Exception as e:
            print(f"[ERROR] Removing pages failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"{str(e)}"}),
                500,
            )

        # Save result PDF
        output_filename = f"{uuid.uuid4()}_removed_pages.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(result_buffer)
            print(f"[INFO] Saved result PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_removed_pages.pdf",
            "message": f"Pages removed successfully",
        }

        print(f"[SUCCESS] {response['message']}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR REMOVE PAGES PAGE ====================


@app.route("/tools/remove-pages.html", methods=["GET"])
def remove_pages_page():
    """Serve remove-pages.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "remove-pages.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== HELPER FUNCTION FOR REORDER PDF ====================


def parse_page_order(page_order_json, total_pages):
    """
    Parse and validate page order JSON

    Args:
        page_order_json: JSON string of page order
        total_pages: Total pages in PDF

    Returns:
        List of page numbers (1-indexed)
    """
    try:
        page_order = json.loads(page_order_json)

        if not isinstance(page_order, list):
            raise ValueError("Page order must be a list")

        if len(page_order) == 0:
            raise ValueError("Page order cannot be empty")

        if len(page_order) != total_pages:
            raise ValueError(
                f"Page order length ({len(page_order)}) does not match total pages ({total_pages})"
            )

        # Validate each page number
        for page_num in page_order:
            if not isinstance(page_num, int):
                raise ValueError(f"Page number must be integer, got {type(page_num)}")
            if page_num < 1 or page_num > total_pages:
                raise ValueError(
                    f"Page number {page_num} out of range (1-{total_pages})"
                )

        return page_order

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to parse page order: {str(e)}")


def reorder_pdf_pages(pdf_buffer, page_order):
    """
    Reorder PDF pages according to provided order

    Args:
        pdf_buffer: PDF file bytes
        page_order: List of page numbers in new order (1-indexed)

    Returns:
        PDF bytes with reordered pages
    """
    try:
        pdf_reader = PdfReader(BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()
        total_pages = len(pdf_reader.pages)

        print(f"[INFO] PDF has {total_pages} pages")
        print(f"[INFO] Reordering to: {page_order}")

        # Add pages in new order
        for idx, page_num in enumerate(page_order):
            # page_num is 1-indexed, PyPDF2 uses 0-indexed
            page = pdf_reader.pages[page_num - 1]
            pdf_writer.add_page(page)
            print(f"[INFO] Added page {page_num} to position {idx + 1}")

        # Write to output buffer
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        output_buffer.seek(0)

        print(f"[SUCCESS] PDF reordered successfully")
        return output_buffer.getvalue()

    except Exception as e:
        raise Exception(f"Failed to reorder PDF: {str(e)}")


# ==================== REORDER PDF API ENDPOINT ====================


@app.route("/api/reorder-pdf", methods=["POST"])
def reorder_pdf_api():
    """Reorder PDF pages endpoint"""
    uploaded_file_path = None

    try:
        print("[API] /api/reorder-pdf called")

        # Debug logging
        print(f"[DEBUG] Form data: {request.form}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")

        # Check for file
        if "file" not in request.files:
            print("[ERROR] No file uploaded")
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        uploaded_file = request.files["file"]

        if not uploaded_file or uploaded_file.filename == "":
            print("[ERROR] No file selected")
            return jsonify({"success": False, "message": "No file selected"}), 400

        print(f"[INFO] Processing: {uploaded_file.filename}")

        # Validate PDF file
        if not uploaded_file.filename.lower().endswith(".pdf"):
            print("[ERROR] File is not PDF")
            return jsonify({"success": False, "message": "Only PDF files allowed"}), 400

        # Get page order
        if "pageOrder" not in request.form:
            print("[ERROR] No page order provided")
            return jsonify({"success": False, "message": "Page order is required"}), 400

        page_order_json = request.form.get("pageOrder", "")

        print(f"[INFO] Page order JSON: {page_order_json}")

        # Save uploaded file
        filename = secure_filename(uploaded_file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            uploaded_file.save(uploaded_file_path)
            print(f"[INFO] Saved uploaded file: {uploaded_file_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save file: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500

        # Get PDF page count
        try:
            pdf_reader = PdfReader(uploaded_file_path)
            total_pages = len(pdf_reader.pages)
        except Exception as e:
            print(f"[ERROR] Could not read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": "Could not read PDF file"}),
                400,
            )

        if total_pages == 0:
            print("[ERROR] PDF has no pages")
            cleanup_file(uploaded_file_path)
            return jsonify({"success": False, "message": "PDF has no pages"}), 400

        print(f"[INFO] Total pages in PDF: {total_pages}")

        # Parse and validate page order
        try:
            page_order = parse_page_order(page_order_json, total_pages)
            print(f"[INFO] Validated page order: {page_order}")
        except ValueError as e:
            print(f"[ERROR] Invalid page order: {str(e)}")
            cleanup_file(uploaded_file_path)
            return jsonify({"success": False, "message": str(e)}), 400

        # Read PDF buffer
        try:
            with open(uploaded_file_path, "rb") as f:
                pdf_buffer = f.read()
            print(f"[INFO] Read PDF buffer: {len(pdf_buffer)} bytes")
        except Exception as e:
            print(f"[ERROR] Failed to read PDF: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to read PDF: {str(e)}"}),
                500,
            )

        # Reorder PDF
        try:
            print(f"[INFO] Starting to reorder PDF...")
            reordered_buffer = reorder_pdf_pages(pdf_buffer, page_order)
            print(f"[INFO] PDF reordered successfully")
        except Exception as e:
            print(f"[ERROR] Reordering failed: {str(e)}")
            print(traceback.format_exc())
            cleanup_file(uploaded_file_path)
            return (
                jsonify(
                    {"success": False, "message": f"Failed to reorder PDF: {str(e)}"}
                ),
                500,
            )

        # Save output PDF
        output_filename = f"{uuid.uuid4()}_reordered.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            with open(output_filepath, "wb") as f:
                f.write(reordered_buffer)
            print(f"[INFO] Saved reordered PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save output: {str(e)}")
            cleanup_file(uploaded_file_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded file
        cleanup_file(uploaded_file_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": f"{os.path.splitext(filename)[0]}_organized.pdf",
            "message": "PDF reordered successfully",
        }

        print(f"[SUCCESS] Response: {response}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large (>50MB)")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] Unexpected error: {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR REORDER PDF PAGE ====================


@app.route("/tools/reorder-pages.html", methods=["GET"])
def reorder_pages_page():
    """Serve reorder-pages.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "reorder-pages.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404


# ==================== SIGN PDF ROUTE ====================
# Add this code to your app.py file


@app.route("/api/sign-pdf", methods=["POST"])
def sign_pdf():
    """
    Sign PDF with signature (draw/upload/text)
    Request form data:
    - file: PDF file
    - signatureMethod: 'draw', 'upload', or 'text'
    - signaturePosition: position on page
    - signaturePage: which page to sign
    - signatureImage: image file (for draw/upload methods)
    - signatureText: text string (for text method)
    - fontSize: font size (for text method)
    - fontFamily: font family (for text method)
    - outputName: output filename
    """
    uploaded_file_path = None
    signature_image_path = None

    try:
        print("\n" + "=" * 80)
        print("[API] Sign PDF Request")
        print("=" * 80)

        # Validate file presence
        if "file" not in request.files:
            print("[ERROR] No file provided")
            return jsonify({"success": False, "message": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            print("[ERROR] Empty filename")
            return jsonify({"success": False, "message": "No file selected"}), 400

        if not allowed_file(file.filename):
            print("[ERROR] Invalid file type")
            return (
                jsonify({"success": False, "message": "Only PDF files are allowed"}),
                400,
            )

        # Get form parameters
        signature_method = request.form.get("signatureMethod", "draw")
        signature_position = request.form.get("signaturePosition", "bottom-right")
        signature_page = request.form.get("signaturePage", "last")
        output_name = request.form.get("outputName", "signed_document.pdf")

        print(f"[INFO] Signature Method: {signature_method}")
        print(f"[INFO] Position: {signature_position}")
        print(f"[INFO] Apply to Page: {signature_page}")

        # Save uploaded PDF
        filename = secure_filename(file.filename)
        uploaded_file_path = os.path.join(
            app.config["UPLOAD_FOLDER"], f"{uuid.uuid4()}_{filename}"
        )
        file.save(uploaded_file_path)
        print(f"[INFO] Saved PDF: {uploaded_file_path}")

        # Read PDF with PyMuPDF
        pdf_document = fitz.open(uploaded_file_path)
        total_pages = len(pdf_document)
        print(f"[INFO] Total pages: {total_pages}")

        # Determine which pages to sign
        if signature_page == "first":
            pages_to_sign = [0]
        elif signature_page == "last":
            pages_to_sign = [total_pages - 1]
        elif signature_page == "all":
            pages_to_sign = list(range(total_pages))
        else:
            pages_to_sign = [total_pages - 1]  # Default to last page

        print(f"[INFO] Pages to sign: {pages_to_sign}")

        # Process signature based on method
        if signature_method in ["draw", "upload"]:
            # Handle image-based signatures
            if "signatureImage" not in request.files:
                cleanup_file(uploaded_file_path)
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "No signature image provided",
                        }
                    ),
                    400,
                )

            signature_file = request.files["signatureImage"]
            if signature_file.filename == "":
                cleanup_file(uploaded_file_path)
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "No signature image selected",
                        }
                    ),
                    400,
                )

            # Save signature image temporarily
            signature_image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                f"{uuid.uuid4()}_signature.png",
            )
            signature_file.save(signature_image_path)
            print(f"[INFO] Saved signature image: {signature_image_path}")

            # Open signature image
            try:
                signature_img = Image.open(signature_image_path)
                # Convert to RGB if necessary
                if signature_img.mode == "RGBA":
                    # Create white background
                    rgb_img = Image.new("RGB", signature_img.size, (255, 255, 255))
                    rgb_img.paste(signature_img, mask=signature_img.split()[3])
                    signature_img = rgb_img
                elif signature_img.mode != "RGB":
                    signature_img = signature_img.convert("RGB")

                # Resize signature to reasonable size (max 200px width)
                max_width = 200
                width, height = signature_img.size
                if width > max_width:
                    ratio = max_width / width
                    new_width = max_width
                    new_height = int(height * ratio)
                    signature_img = signature_img.resize(
                        (new_width, new_height), Image.Resampling.LANCZOS
                    )

                # Save resized image
                temp_signature_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    f"{uuid.uuid4()}_signature_resized.png",
                )
                signature_img.save(temp_signature_path, format="PNG")

            except Exception as e:
                print(f"[ERROR] Failed to process signature image: {str(e)}")
                cleanup_file(uploaded_file_path)
                cleanup_file(signature_image_path)
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Failed to process signature: {str(e)}",
                        }
                    ),
                    500,
                )

            # Apply signature to specified pages
            for page_num in pages_to_sign:
                page = pdf_document[page_num]
                page_width = page.rect.width
                page_height = page.rect.height

                # Get signature dimensions
                sig_width, sig_height = signature_img.size

                # Calculate position
                margin = 20
                if signature_position == "bottom-right":
                    x = page_width - sig_width - margin
                    y = page_height - sig_height - margin
                elif signature_position == "bottom-left":
                    x = margin
                    y = page_height - sig_height - margin
                elif signature_position == "bottom-center":
                    x = (page_width - sig_width) / 2
                    y = page_height - sig_height - margin
                elif signature_position == "top-right":
                    x = page_width - sig_width - margin
                    y = margin
                elif signature_position == "top-left":
                    x = margin
                    y = margin
                elif signature_position == "center":
                    x = (page_width - sig_width) / 2
                    y = (page_height - sig_height) / 2
                else:
                    x = page_width - sig_width - margin
                    y = page_height - sig_height - margin

                # Insert image
                rect = fitz.Rect(x, y, x + sig_width, y + sig_height)
                page.insert_image(rect, filename=temp_signature_path)

            # Cleanup temporary signature file
            cleanup_file(temp_signature_path)

        elif signature_method == "text":
            # Handle text-based signatures
            signature_text = request.form.get("signatureText", "").strip()
            if not signature_text:
                cleanup_file(uploaded_file_path)
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "No signature text provided",
                        }
                    ),
                    400,
                )

            font_size = int(request.form.get("fontSize", 36))
            font_family = request.form.get("fontFamily", "Helvetica")

            print(f"[INFO] Signature Text: {signature_text}")
            print(f"[INFO] Font Size: {font_size}")
            print(f"[INFO] Font Family: {font_family}")

            # Map font families to PyMuPDF fonts
            font_mapping = {
                "Helvetica": "helv",
                "Courier": "cour",
                "Times-Roman": "tiro",
            }
            pymupdf_font = font_mapping.get(font_family, "helv")

            # Apply text signature to specified pages
            for page_num in pages_to_sign:
                page = pdf_document[page_num]
                page_width = page.rect.width
                page_height = page.rect.height

                # Calculate text dimensions (approximate)
                text_width = len(signature_text) * (font_size * 0.6)
                text_height = font_size

                # Calculate position
                margin = 20
                if signature_position == "bottom-right":
                    x = page_width - text_width - margin
                    y = page_height - margin
                elif signature_position == "bottom-left":
                    x = margin
                    y = page_height - margin
                elif signature_position == "bottom-center":
                    x = (page_width - text_width) / 2
                    y = page_height - margin
                elif signature_position == "top-right":
                    x = page_width - text_width - margin
                    y = margin + text_height
                elif signature_position == "top-left":
                    x = margin
                    y = margin + text_height
                elif signature_position == "center":
                    x = (page_width - text_width) / 2
                    y = (page_height + text_height) / 2
                else:
                    x = page_width - text_width - margin
                    y = page_height - margin

                # Insert text
                point = fitz.Point(x, y)
                page.insert_text(
                    point,
                    signature_text,
                    fontsize=font_size,
                    fontname=pymupdf_font,
                    color=(0, 0, 0),
                )

        else:
            cleanup_file(uploaded_file_path)
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Invalid signature method: {signature_method}",
                    }
                ),
                400,
            )

        # Save signed PDF
        output_filename = f"{uuid.uuid4()}_signed.pdf"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)

        try:
            pdf_document.save(output_filepath)
            pdf_document.close()
            print(f"[INFO] Saved signed PDF: {output_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to save output: {str(e)}")
            cleanup_file(uploaded_file_path)
            if signature_image_path:
                cleanup_file(signature_image_path)
            return (
                jsonify({"success": False, "message": f"Failed to save: {str(e)}"}),
                500,
            )

        # Cleanup uploaded files
        cleanup_file(uploaded_file_path)
        if signature_image_path:
            cleanup_file(signature_image_path)

        response = {
            "success": True,
            "downloadUrl": f"/api/download-pdf/{output_filename}",
            "filename": output_name,
            "message": "PDF signed successfully",
        }

        print(f"[SUCCESS] Response: {response}")
        return jsonify(response), 200

    except RequestEntityTooLarge:
        print("[ERROR] File too large (>50MB)")
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        if signature_image_path:
            cleanup_file(signature_image_path)
        return (
            jsonify({"success": False, "message": "File size exceeds 50MB limit"}),
            413,
        )

    except Exception as e:
        print(f"[ERROR] Unexpected error: {str(e)}")
        print(traceback.format_exc())
        if uploaded_file_path:
            cleanup_file(uploaded_file_path)
        if signature_image_path:
            cleanup_file(signature_image_path)
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ==================== STATIC ROUTE FOR SIGN PDF PAGE ====================


@app.route("/tools/sign-pdf.html", methods=["GET"])
def sign_pdf_page():
    """Serve sign-pdf.html"""
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(PROJECT_ROOT, "tools", "sign-pdf.html")
    if os.path.exists(tools_path):
        return send_file(tools_path, mimetype="text/html")
    return jsonify({"error": "File not found"}), 404




# ==================== DOWNLOAD ROUTES ====================


@app.route("/api/download-pdf/<filename>", methods=["GET"])
def download_pdf(filename):
    """Download PDF file"""
    try:
        print(f"[API] Download PDF: {filename}")

        filename = secure_filename(filename)
        filepath = os.path.join(app.config["OUTPUT_FOLDER"], filename)

        if not os.path.exists(filepath):
            return jsonify({"success": False, "message": "File not found"}), 404

        print(f"[INFO] Serving: {filepath}")

        return send_file(
            filepath,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="document.pdf",
        )

    except Exception as e:
        print(f"[ERROR] Download error: {str(e)}")
        return jsonify({"success": False, "message": f"Download error: {str(e)}"}), 500


@app.route("/api/download-zip/<filename>", methods=["GET"])
def download_zip(filename):
    """Download ZIP file"""
    try:
        print(f"[API] Download ZIP: {filename}")

        filename = secure_filename(filename)
        filepath = os.path.join(app.config["OUTPUT_FOLDER"], filename)

        if not os.path.exists(filepath):
            return jsonify({"success": False, "message": "File not found"}), 404

        print(f"[INFO] Serving: {filepath}")

        return send_file(
            filepath,
            mimetype="application/zip",
            as_attachment=True,
            download_name="split_document.zip",
        )

    except Exception as e:
        print(f"[ERROR] Download error: {str(e)}")
        return jsonify({"success": False, "message": f"Download error: {str(e)}"}), 500


# ==================== HEALTH CHECK ====================


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return (
        jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "project_root": PROJECT_ROOT,
                "features": [
                    "merge-pdf",
                    "split-pdf",
                    "protect-pdf",
                    "unlock-pdf",
                    "image-to-pdf",
                    "pdf-to-jpg",
                    "rotate-pdf",
                    "compress-pdf",
                    "add-page-numbers",
                    "add-watermark",
                    "remove-pages",
                    "reorder-pages",
                    "sign-pdf",
                ],
            }
        ),
        200,
    )


# ==================== ERROR HANDLERS ====================


@app.errorhandler(400)
def bad_request(error):
    print("[ERROR] 400 Bad Request")
    return jsonify({"success": False, "message": "Bad request"}), 400


@app.errorhandler(404)
def not_found(error):
    print("[ERROR] 404 Not Found")
    return jsonify({"success": False, "message": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(error):
    print("[ERROR] 500 Server Error")
    return jsonify({"success": False, "message": "Internal server error"}), 500


@app.errorhandler(413)
def request_entity_too_large(error):
    print("[ERROR] 413 File Too Large")
    return jsonify({"success": False, "message": "File size exceeds 50MB limit"}), 413


# ==================== MAIN ====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV", "production") == "development"

    print("\n" + "=" * 80)
    print("PDF TOOLKIT - Flask Backend (All 13 Tools - 100% Working)")
    print("=" * 80)
    print(f"\n[STARTUP] Starting server on http://0.0.0.0:{port}")
    print(f"[STARTUP] Debug Mode: {debug_mode}")
    print(f"[STARTUP] Max File Size: 50MB\n")
    print("[ROUTES] Available Endpoints:")
    print(f"  • Home: http://localhost:{port}/")
    print(f"  • Merge Tool: http://localhost:{port}/tools/merge-pdf.html")
    print(f"  • Split Tool: http://localhost:{port}/tools/split-pdf.html")
    print(f"  • Protect Tool: http://localhost:{port}/tools/protect-pdf.html")
    print(f"  • Unlock Tool: http://localhost:{port}/tools/unlock-pdf.html")
    print(f"  • Image to PDF Tool: http://localhost:{port}/tools/image-to-pdf.html")
    print(f"  • PDF to JPG Tool: http://localhost:{port}/tools/pdf-to-jpg.html")
    print(f"  • Rotate PDF Tool: http://localhost:{port}/tools/rotate-pdf.html")
    print(f"  • Compress PDF Tool: http://localhost:{port}/tools/compress-pdf.html")
    print(
        f"  • Add Page Numbers Tool: http://localhost:{port}/tools/add-page-numbers.html"
    )
    print(f"  • Add Watermark Tool: http://localhost:{port}/tools/add-watermark.html")
    print(f"  • Remove Pages Tool: http://localhost:{port}/tools/remove-pages.html")
    print(f"  • Reorder Pages Tool: http://localhost:{port}/tools/reorder-pages.html")
    print(f"  • Sign PDF Tool: http://localhost:{port}/tools/sign-pdf.html")
    print(f"\n[API] Available APIs:")
    print(f"  • POST http://localhost:{port}/api/merge-pdf")
    print(f"  • POST http://localhost:{port}/api/split-pdf")
    print(f"  • POST http://localhost:{port}/api/protect-pdf")
    print(f"  • POST http://localhost:{port}/api/unlock-pdf")
    print(f"  • POST http://localhost:{port}/api/image-to-pdf")
    print(f"  • POST http://localhost:{port}/api/pdf-to-jpg")
    print(f"  • POST http://localhost:{port}/api/rotate-pdf")
    print(f"  • POST http://localhost:{port}/api/compress-pdf")
    print(f"  • POST http://localhost:{port}/api/add-page-numbers")
    print(f"  • POST http://localhost:{port}/api/add-watermark")
    print(f"  • POST http://localhost:{port}/api/remove-pages")
    print(f"  • POST http://localhost:{port}/api/reorder-pages")
    print(f"  • POST http://localhost:{port}/api/sign-pdf")
    print(f"  • GET http://localhost:{port}/api/download-pdf/<filename>")
    print(f"  • GET http://localhost:{port}/api/download-zip/<filename>")
    print(f"  • GET http://localhost:{port}/api/health")
    print("\n" + "=" * 80 + "\n")

    app.run(host="0.0.0.0", port=port, debug=debug_mode)
