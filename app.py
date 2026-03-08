import os
import csv
import io
import json
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
from flask import Flask, render_template, request, make_response

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image as RLImage
from reportlab.lib import colors

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

PDF_DIR    = os.path.join(os.path.dirname(__file__), 'generated_pdfs')
DOCTOR_IMG = os.path.join(os.path.dirname(__file__), 'static', 'doctor-symbol-b.png')
SHEET_ID   = '10coRevhuITB8RhqYGrUGCdDtuVC9eq1rynGMzDZ81s0'
FIELDS     = ['Timestamp', 'Name', 'Age', 'Gender', 'Date', 'Address', 'Mobile', 'Doctor', 'Category', 'Prant', 'Dayitva']

DOCTORS = {
    'Dr. RC Roy':            {'degree': 'M.S. Surgery',  'reg': 'Reg. No. 8054 BIHAR'},
    'Dr. Nirmal Khandelwal': {'degree': 'M.D. Medicine', 'reg': 'Reg. No. HN 162'},
    'Dr. Ravinder':          {'degree': 'M.B.B.S',       'reg': 'Reg. No. HN 24930'},
}

os.makedirs(PDF_DIR, exist_ok=True)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

_sheet_cache = None


def get_sheet():
    global _sheet_cache
    if _sheet_cache is not None:
        return _sheet_cache

    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise RuntimeError('GOOGLE_CREDENTIALS is not configured.')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1

    # Add header row if empty, or patch any missing columns
    existing = sheet.row_values(1)
    if not existing:
        sheet.insert_row(FIELDS, index=1)
    else:
        for i, field in enumerate(FIELDS):
            if i >= len(existing) or existing[i] != field:
                sheet.update_cell(1, i + 1, field)

    _sheet_cache = sheet
    return sheet


def read_entries():
    return get_sheet().get_all_records()


def append_entry(data: dict):
    row = [data.get(f, '') for f in FIELDS]
    get_sheet().append_row(row, value_input_option='USER_ENTERED')


def generate_pdf(name, age, gender, date, address, mobile, doctor) -> bytes:
    buf = io.BytesIO()

    LEFT  = 2.54 * cm
    RIGHT = 2.54 * cm
    W, H  = A4

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=0.6 * cm,
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

    if os.path.exists(DOCTOR_IMG):
        img = RLImage(DOCTOR_IMG, width=2 * cm, height=2 * cm)
        img.hAlign = 'CENTER'
        story.append(img)
        story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph('MADHAV SHRISHTI, Pattikalyana', header_style))
    story.append(Paragraph('Dist. Panipat', subheader_style))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.black, spaceAfter=10))

    def field_line(label, value):
        return Paragraph(f'<b>{label}</b> {value}', field_style)

    story.append(field_line('Name:', name))
    story.append(field_line('Age:', age))
    story.append(field_line('Gender:', gender))
    story.append(field_line('Date:', date))
    story.append(field_line('Address:', address))
    story.append(field_line('Mobile:', mobile))

    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.grey, spaceAfter=6))

    doc_info = DOCTORS.get(doctor, {})
    doc_degree = doc_info.get('degree', '')
    doc_reg    = doc_info.get('reg', '')

    def draw_signature(canvas, doc):
        canvas.saveState()
        x_right = W - RIGHT
        x_left  = x_right - 6 * cm

        # Three lines of text, stacked upward from 20% height
        line_height = 0.55 * cm
        reg_y    = H * 0.20
        degree_y = reg_y    + line_height
        name_y   = degree_y + line_height
        rule_y   = name_y   + 0.5 * cm

        canvas.setLineWidth(0.5)
        canvas.line(x_left, rule_y, x_right, rule_y)

        canvas.setFont('Helvetica-Bold', 11)
        canvas.drawRightString(x_right, name_y, doctor)
        canvas.setFont('Helvetica', 10)
        canvas.drawRightString(x_right, degree_y, doc_degree)
        canvas.drawRightString(x_right, reg_y, doc_reg)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_signature, onLaterPages=draw_signature)
    return buf.getvalue()


@app.route('/', methods=['GET'])
def index():
    try:
        entries = read_entries()
        sheet_error = None
    except Exception as e:
        entries = []
        sheet_error = str(e)
    return render_template('index.html', entries=entries, sheet_error=sheet_error)


@app.route('/generate', methods=['POST'])
def generate():
    name    = request.form.get('name', '').strip()
    age     = request.form.get('age', '').strip()
    gender  = request.form.get('gender', '').strip()
    date    = request.form.get('date', '').strip()
    address = request.form.get('address', '').strip()
    mobile  = request.form.get('mobile', '').strip()
    doctor   = request.form.get('doctor', '').strip()
    category = request.form.get('category', '').strip()
    prant    = request.form.get('prant', '').strip()
    dayitva  = request.form.get('dayitva', '').strip()

    errors = []
    if not name:     errors.append('Name is required.')
    if not age:      errors.append('Age is required.')
    if not gender:   errors.append('Gender is required.')
    if not date:     errors.append('Date is required.')
    if not address:  errors.append('Address is required.')
    if not mobile:   errors.append('Mobile number is required.')
    if not doctor:   errors.append('Doctor is required.')
    if not category: errors.append('Category is required.')

    if errors:
        try:
            entries = read_entries()
            sheet_error = None
        except Exception as e:
            entries = []
            sheet_error = str(e)
        return render_template('index.html', entries=entries, errors=errors,
                               form_data=request.form, sheet_error=sheet_error), 400

    timestamp = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    append_entry({
        'Timestamp': timestamp,
        'Name': name,
        'Age': age,
        'Gender': gender,
        'Date': date,
        'Address': address,
        'Mobile': mobile,
        'Doctor': doctor,
        'Category': category,
        'Prant': prant,
        'Dayitva': dayitva,
    })

    pdf_bytes = generate_pdf(name, age, gender, date, address, mobile, doctor)

    safe_name    = ''.join(c if c.isalnum() else '_' for c in name)
    pdf_filename = f'{safe_name}_{timestamp.replace(":", "-").replace(" ", "_")}.pdf'

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
    return response


@app.route('/export-csv', methods=['GET'])
def export_csv():
    entries = read_entries()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(entries)
    response = make_response(buf.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename="entries.csv"'
    return response


if __name__ == '__main__':
    app.run(debug=True, port=5050)
