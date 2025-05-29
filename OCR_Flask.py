import re
import pytesseract
from PIL import Image
import io
import fitz  # PyMuPDF
import os
import argparse
import tempfile
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Text Extraction Functions ---

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF using PyTesseract."""
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang='eng', config='--psm 6')
        full_text += text + "\n"
    doc.close()
    return full_text

def extract_text_from_image(image_path):
    """Extract text from an image using PyTesseract."""
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang='eng', config='--psm 6')
    return text

# --- Clinical Value Extraction ---

def extract_health_values(text):
    lines = text.splitlines()
    # Patterns for clinical metrics
    patterns = {
        "Plasma Glucose": re.compile(r'\b(?:Plasma\s*Glucose|Plasma\s*Glu|Glu\s*\(Plasma\)|Glucose,\s*Plasma|P-Glucose|Plazma\s*Glucose|Plasma\s*Glukose)\b', re.IGNORECASE),
        "HbA1c": re.compile(r'\b(?:HbA1c|A1c|HbAic|HbAIc|H6A1c|HbAlc|Glycosylated Hemoglobin|HgbA1c|Hemoglobin A1c|HbA1C|HBA1c|Hemogloben A1c)\b', re.IGNORECASE),
        "HDL": re.compile(r'\b(?:HDL|HDL-C|High-density Lipoprotein|HDLc)\b', re.IGNORECASE),
        "LDL": re.compile(r'\b(?:LDL|LDL-C|Low-density Lipoprotein|LDLc)\b', re.IGNORECASE),
        "Triglycerides": re.compile(r'\b(?:Triglycerides|Triglyceride|Trigs|Trig)\b', re.IGNORECASE),
        "Albumin": re.compile(r'\b(?:Serum Albumin|Albumin|Albm|Albumn|Albmin)\b', re.IGNORECASE),
        "Cholesterol": re.compile(r'\b(?:Total Cholesterol|Cholesterol|Cholestrol|Chol|Tot Chol)\b', re.IGNORECASE),
        "BMI": re.compile(r'\b(?:BMI|Body Mass Index|B\.M\.I\.)\b', re.IGNORECASE),
        "Blood Pressure": re.compile(r'\b(?:Blood Pressure|BP|B\.P\.|BloodPressure)\b', re.IGNORECASE),
        "TSH": re.compile(r'\b(?:TSH|Thyroid Stimulating Hormone|T\.S\.H\.|Thyrotropin|THS|Tyroid Stimulating Hormone)\b', re.IGNORECASE),
        "LDH": re.compile(r'\b(?:LDH|LD|Lactate Dehydrogenase|LD Value|LHD|Lactate Dehidrogenase)\b', re.IGNORECASE),
        "CK": re.compile(r'\b(?:CK|Creatine Kinase|CPK|Creatine Phosphokinase|Creatin Kinase|CKK|Cretine Kinase)\b', re.IGNORECASE)
    }
    num_pat = re.compile(r'\b([0-9]+[.,]?[0-9]*)\b')
    bp_pat = re.compile(r'([0-9]{2,3}/[0-9]{2,3})')

    results = {}
    for i, line in enumerate(lines):
        clean_line = re.sub(r'\(.*?\)', '', line)
        clean_line = re.sub(r'\s+', ' ', clean_line).strip()
        print(f"Line {i+1}: '{line}' (cleaned: '{clean_line}')")
        for key, pattern in patterns.items():
            if key not in results:
                m = pattern.search(clean_line)
                if m:
                    print(f"  - Matched '{key}' in line {i+1}")
                    if key == "Blood Pressure":
                        m_bp = bp_pat.search(clean_line, m.end())
                        if m_bp:
                            value = m_bp.group(1)
                            print(f"    - Found Blood Pressure value '{value}'")
                            results[key] = value
                    else:
                        m_num = num_pat.search(clean_line, m.end())
                        if m_num:
                            value = m_num.group(1).replace(',', '.')
                            print(f"    - Found value '{value}' for '{key}'")
                            results[key] = value

    # Set missing tests to None
    for key in patterns:
        if key not in results:
            results[key] = None
    return results

# --- Flask Route ---

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.pdf', '.jpg', '.jpeg', '.png']:
        return jsonify({'error': 'Unsupported file type'}), 400
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            file.save(temp_file.name)
            if ext == '.pdf':
                text = extract_text_from_pdf(temp_file.name)
            else:
                text = extract_text_from_image(temp_file.name)
            health_values = extract_health_values(text)
            return jsonify({'extracted_values': health_values}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)

# --- Command-Line Testing ---

def main():
    parser = argparse.ArgumentParser(description="Extract clinical data from a medical report.")
    parser.add_argument("--file", required=True, help="Path to the PDF or image file")
    args = parser.parse_args()

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        return

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        text = extract_text_from_pdf(file_path)
    elif ext in ['.jpg', '.jpeg', '.png']:
        text = extract_text_from_image(file_path)
    else:
        print(f"Error: Unsupported file extension '{ext}'. Use PDF, JPG, JPEG, or PNG.")
        return

    print("=== Extracted Text ===")
    print(text)

    health_values = extract_health_values(text)
    print("\n✔️ Extracted Health Values:")
    for key, value in health_values.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    if len(os.sys.argv) == 1:
        app.run(host='0.0.0.0', port=5000)
    else:
        main()