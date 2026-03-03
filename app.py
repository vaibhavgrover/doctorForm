import os
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, send_file, make_response

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

app = Flask(__name__)

CSV_FILE = os.path.join(os.path.dirname(__file__), 'entries.csv')
PDF_DIR = os.path.join(os.path.dirname(__file__), 'generated_pdfs')
DOCTOR_IMG = os.path.join(os.path.dirname(__file__), 'doctor-symbol-b.png')

CSV_FIELDS = ['Timestamp', 'Name', 'Age', 'Date', 'Address', 'Mobile']

os.makedirs(PDF_DIR, exist_ok=True)


def ensure_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def read_entries():
    ensure_csv()
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def append_entry(data: dict):
    ensure_csv()
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow(data)


def generate_pdf(name, age, date, address, mobile) -> bytes:
    buf = io.BytesIO()

    LEFT = 2.54 * cm
    RIGHT = 2.54 * cm
    W, H = A4

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=0.6 * cm,   # tight top — header starts near the top
        bottomMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'header',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    subheader_style = ParagraphStyle(
        'subheader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    field_style = ParagraphStyle(
        'field',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        alignment=TA_LEFT,
        spaceAfter=6,
        leading=16,
    )

    story = []

    # Doctor symbol image (top center)
    if os.path.exists(DOCTOR_IMG):
        img = RLImage(DOCTOR_IMG, width=2 * cm, height=2 * cm)
        img.hAlign = 'CENTER'
        story.append(img)
        story.append(Spacer(1, 0.2 * cm))

    # Header
    story.append(Paragraph('MADHAV SHRISHTI, Pattikalyana', header_style))
    story.append(Paragraph('Dist. Panipat', subheader_style))

    # Horizontal rule
    story.append(HRFlowable(width='100%', thickness=1, color=colors.black, spaceAfter=10))

    # Fields
    def field_line(label, value):
        return Paragraph(f'<b>{label}</b> {value}', field_style)

    story.append(field_line('Name:', name))
    story.append(field_line('Age:', age))
    story.append(field_line('Date:', date))
    story.append(field_line('Address:', address))
    story.append(field_line('Mobile:', mobile))

    # Horizontal rule after fields
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.grey, spaceAfter=6))

    # Draw "Doctor's Signature" pinned to near-bottom via canvas callback
    def draw_signature(canvas, doc):
        canvas.saveState()
        sig_y = 1.8 * cm          # baseline of text from page bottom
        line_y = sig_y + 0.5 * cm # short rule just above the text
        x_right = W - RIGHT
        x_left  = x_right - 5 * cm

        canvas.setLineWidth(0.5)
        canvas.line(x_left, line_y, x_right, line_y)

        canvas.setFont('Helvetica', 11)
        canvas.drawRightString(x_right, sig_y, "Doctor's Signature")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_signature, onLaterPages=draw_signature)
    return buf.getvalue()


@app.route('/', methods=['GET'])
def index():
    entries = read_entries()
    return render_template('index.html', entries=entries)


@app.route('/generate', methods=['POST'])
def generate():
    name    = request.form.get('name', '').strip()
    age     = request.form.get('age', '').strip()
    date    = request.form.get('date', '').strip()
    address = request.form.get('address', '').strip()
    mobile  = request.form.get('mobile', '').strip()

    # Basic validation
    errors = []
    if not name:    errors.append('Name is required.')
    if not age:     errors.append('Age is required.')
    if not date:    errors.append('Date is required.')
    if not address: errors.append('Address is required.')
    if not mobile:  errors.append('Mobile number is required.')

    if errors:
        entries = read_entries()
        return render_template('index.html', entries=entries, errors=errors,
                               form_data=request.form), 400

    # Record in CSV
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    append_entry({
        'Timestamp': timestamp,
        'Name': name,
        'Age': age,
        'Date': date,
        'Address': address,
        'Mobile': mobile,
    })

    # Generate PDF
    pdf_bytes = generate_pdf(name, age, date, address, mobile)

    # Save to disk too
    safe_name = ''.join(c if c.isalnum() else '_' for c in name)
    pdf_filename = f'{safe_name}_{timestamp.replace(":", "-").replace(" ", "_")}.pdf'
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)

    # Return PDF for download
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
    return response


@app.route('/export-csv', methods=['GET'])
def export_csv():
    ensure_csv()
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        csv_data = f.read()
    response = make_response(csv_data)
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename="entries.csv"'
    return response


if __name__ == '__main__':
    app.run(debug=True, port=5050)
