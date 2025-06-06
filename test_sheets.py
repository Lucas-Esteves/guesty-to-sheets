import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

# Autenticación con Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
client = gspread.authorize(credentials)

# Intentar abrir la planilla
try:
    sheet = client.open("Prueba").sheet1
    sheet.append_row(["✅ Conexión exitosa"])
    print("✅ Se escribió correctamente en el Excel.")
except Exception as e:
    print("❌ ERROR al escribir en el Excel:")
    print(e)
