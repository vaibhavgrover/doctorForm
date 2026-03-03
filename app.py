import os
import csv
import io
import json
from datetime import datetime
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
FIELDS     = ['Timestamp', 'Name', 'Age', 'Date', 'Address', 'Mobile']

os.makedirs(PDF_DIR, exist_ok=True)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]


def get_sheet():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise RuntimeError('GOOGLE_CREDENTIALS environment variable is not set.')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1

    # Write header row if the sheet is empty
    if sheet.row_count == 0 or sheet.cell(1, 1).value != 'Timestamp':
        sheet.insert_row(FIELDS, index=1)

    return sheet


def read_entries():
    sheet = get_sheet()
    rows = sheet.get_all_records()   # list of dicts, skips header automatically
    return rows


def append_entry(data: dict):
    sheet = get_sheet()
    row = [data.get(f, '') for f in FIELDS]
    sheet.append_row(row, value_input_option='USER_ENTERED')


def generate_pdf(name, age, date, address, mobile) -> bytes:
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
    story.append(field_line('Date:', date))
    story.append(field_line('Address:', address))
    story.append(field_line('Mobile:', mobile))

    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.grey, spaceAfter=6))

    def draw_signature(canvas, doc):
        canvas.saveState()
        sig_y  = 1.8 * cm
        line_y = sig_y + 0.5 * cm
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
    date    = request.form.get('date', '').strip()
    address = request.form.get('address', '').strip()
    mobile  = request.form.get('mobile', '').strip()

    errors = []
    if not name:    errors.append('Name is required.')
    if not age:     errors.append('Age is required.')
    if not date:    errors.append('Date is required.')
    if not address: errors.append('Address is required.')
    if not mobile:  errors.append('Mobile number is required.')

    if errors:
        try:
            entries = read_entries()
            sheet_error = None
        except Exception as e:
            entries = []
            sheet_error = str(e)
        return render_template('index.html', entries=entries, errors=errors,
                               form_data=request.form, sheet_error=sheet_error), 400

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    append_entry({
        'Timestamp': timestamp,
        'Name': name,
        'Age': age,
        'Date': date,
        'Address': address,
        'Mobile': mobile,
    })

    pdf_bytes = generate_pdf(name, age, date, address, mobile)

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
