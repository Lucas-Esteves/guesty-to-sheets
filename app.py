# forzar deploy en Render
import sys
print("Iniciando app... Python versión:", sys.version)
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import os
import json

app = Flask(__name__)

# Autenticación con Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
client = gspread.authorize(credentials)

# Abrir la hoja de cálculo
sheet = client.open("Prueba").sheet1

@app.route("/", methods=["GET"])
def home():
    return "Running OK"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("===== NUEVO EVENTO WEBHOOK =====")
    print(json.dumps(data, indent=2))  # Mostramos la data bien formateada en logs de Render

    return "OK", 200


@app.route("/test-sheets", methods=["GET"])
def test_sheets():
    try:
        now = datetime.datetime.now().isoformat()
        sheet.append_row(["✅ Conexión exitosa", now])
        return "Conexión exitosa con Google Sheets", 200
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

if __name__ == "__main__":
    print("Iniciando servidor...")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
