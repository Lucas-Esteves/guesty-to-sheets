import os
from flask import Flask, request, jsonify
import gspread
import json
from dotenv import load_dotenv

# Cargar variables de entorno al inicio
load_dotenv()

app = Flask(__name__)

# --- INICIALIZACIÓN DE GOOGLE SHEETS (SE EJECUTA UNA SOLA VEZ AL INICIAR LA APP) ---
gc = None
spreadsheet = None
worksheet = None

try:
    google_credentials_str = os.getenv('GOOGLE_CREDENTIALS')
    if not google_credentials_str:
        raise ValueError("GOOGLE_CREDENTIALS no está configurada.")

    credentials_info = json.loads(google_credentials_str)
    gc = gspread.service_account_from_dict(credentials_info)

    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    if not spreadsheet_id:
        raise ValueError("SPREADSHEET_ID no está configurada.")

    range_name = os.getenv('RANGE_NAME')
    if not range_name:
        raise ValueError("RANGE_NAME no está configurada.")

    spreadsheet = gc.open_by_id(spreadsheet_id)
    worksheet = spreadsheet.worksheet(range_name)
    print("✅ Google Sheets client inicializado con éxito.")
except Exception as e:
    print(f"❌ ERROR al inicializar Google Sheets client: {e}")
    # La aplicación continuará, pero las solicitudes al webhook fallarán si gc/worksheet no están inicializados

# --- RUTA DEL WEBHOOK ---
@app.route('/webhook', methods=['POST'])
def webhook():
    # Verificar si el cliente de Google Sheets se inicializó correctamente
    if not gc or not spreadsheet or not worksheet:
        print("🚫 Google Sheets client no inicializado. No se puede procesar el webhook.")
        return jsonify({"status": "error", "message": "Server error: Google Sheets client not ready"}), 500

    try:
        data = request.json # Obtener el JSON del webhook de Guesty

        # --- LÓGICA PARA PROCESAR LOS DATOS DE GUESTY Y ESCRIBIR EN SHEETS ---
        # Basado en el payload de ejemplo que enviaste (reservation.updated)
        # Adapta esta lista de 'values' si tus columnas en Google Sheets son diferentes o quieres otro orden
        values = [
            data.get('event', ''),
            data.get('eventId', ''),
            data.get('messageId', ''),
            data.get('reservation_id', ''),
            data.get('accountId', ''),
            data.get('guestId', ''),
            data.get('listingId', ''),
            data.get('checkIn', ''),
            data.get('checkOut', ''),
            data.get('numberOfGuests', ''),
            data.get('platform', ''),
            data.get('reservationStatus', ''),
            data.get('guestFirstName', ''),
            data.get('guestLastName', ''),
            data.get('totalAmount', ''),
            data.get('cleaningFees', ''),
            data.get('serviceFees', ''),
            data.get('securityDeposit', ''),
            data.get('listing_name', ''),
            data.get('listing_city', ''),
            data.get('guest_email', ''),
            data.get('guest_phone', ''),
            data.get('nights', '')
        ]

        worksheet.append_row(values) # Añadir la fila con los valores

        print("✔️ Webhook procesado y datos escritos en Google Sheets.")
        return jsonify({"status": "success", "message": "Datos procesados y guardados"}), 200

    except Exception as e:
        print(f"❌ ERROR al procesar webhook o escribir en Sheets: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Esto es solo para ejecución local (si corres python app.py), Render usa gunicorn
    app.run(debug=True, host='0.0.0.0', port=os.getenv('PORT', 5000))