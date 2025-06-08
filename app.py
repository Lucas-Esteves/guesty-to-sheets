import os
import json
import base64
from flask import Flask, request, jsonify # Importar jsonify para las respuestas
import gspread # Gspread no se usa directamente en este código, pero puede ser una dependencia de las librerías de Google
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv # Para cargar variables de entorno en local, si aplica

# Cargar variables de entorno al inicio (para desarrollo local)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURACIÓN GLOBAL DE GOOGLE SHEETS ---
# Estas variables son constantes y se leerán al inicio
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1UqW44Uu1r44mDX6_UBn0MSox9cIiW4E6Zmm7xQ9AWm8")
RANGE_NAME = os.getenv("RANGE_NAME", 'test')

# Define el orden de las columnas en tu Google Sheet
# ¡Asegúrate de que tu hoja de cálculo tenga estas columnas y en este orden!
field_names = [
    "event", "eventId", "messageId", "reservation_id", "accountId", "guestId", "listingId",
    "checkIn", "checkOut", "numberOfGuests", "platform", "reservationStatus", "guestFirstName",
    "guestLastName", "totalAmount", "cleaningFee", "serviceFee", "securityDeposit",
    "listing_name", "listing_city", "guest_email", "guest_phone", "nights"
]

# --- INICIALIZACIÓN GLOBAL DEL SERVICIO DE GOOGLE SHEETS ---
# Estas variables se inicializarán una sola vez al arrancar la aplicación
sheets_service = None # La instancia del servicio de Google Sheets

try:
    google_credentials = os.getenv("GOOGLE_CREDENTIALS")
    if google_credentials is None:
        raise ValueError("La variable de entorno 'GOOGLE_CREDENTIALS' no está configurada.")

    # Decodificar la cadena base64 de las credenciales
    # La cadena debe ser un JSON de credenciales de cuenta de servicio codificado en Base64
    service_account_info = json.loads(base64.b64decode(google_credentials))
    creds = Credentials.from_service_account_info(service_account_info)
    
    # Construir el servicio de Sheets una sola vez
    sheets_service = build("sheets", "v4", credentials=creds)
    print("✅ Servicio de Google Sheets inicializado con éxito.")

except Exception as e:
    print(f"❌ ERROR CRÍTICO al inicializar el servicio de Google Sheets: {e}")
    sheets_service = None # Asegurarse de que el servicio no esté disponible si falla la inicialización

# --- Función para asegurar la fila de encabezado ---
# Esta función ahora usa la variable global sheets_service
def ensure_header_row_exists_global():
    if sheets_service is None:
        print("🚫 Servicio de Google Sheets no inicializado. No se puede verificar/añadir encabezado.")
        raise RuntimeError("Servicio de Google Sheets no disponible.")

    sheet_instance = sheets_service.spreadsheets() # Obtener la instancia del servicio de hojas de cálculo

    try:
        result = sheet_instance.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])

        if not values or values[0] != field_names: # Comprueba si no hay valores o si el encabezado no coincide
            print("Header row missing or incorrect. Adding/Updating header.")
            body = {"values": [field_names]}
            sheet_instance.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{RANGE_NAME}!A1", # Escribir siempre en la primera fila
                valueInputOption="RAW",
                body=body
            ).execute()
            print("✅ Header row ensured in Google Sheets")
        else:
            print("✅ Header row already exists and is correct in Google Sheets")

    except HttpError as error:
        print(f"❌ An error occurred with Google Sheets API during header check: {error}")
        raise
    except Exception as e:
        print(f"❌ Error ensuring header row exists: {str(e)}")
        raise

# --- Función para actualizar Google Sheets ---
# Esta función ahora usa la variable global sheets_service
def update_google_sheets(data):
    if sheets_service is None:
        print("🚫 Servicio de Google Sheets no inicializado. No se puede actualizar.")
        return {"message": "Server error: Google Sheets service not ready"}, 500

    sheet_instance = sheets_service.spreadsheets() # Obtener la instancia del servicio de hojas de cálculo

    try:
        # Asegurar que la fila de encabezado exista antes de procesar datos
        # Llama a la función global, que no inicializa el servicio de nuevo
        ensure_header_row_exists_global() 

        reservation_data = data.get("reservation", {})
        if not reservation_data:
            print("Reservation data is missing in the request")
            return {"message": "Reservation data is missing"}, 400

        reservation_id = reservation_data.get("_id")
        if not reservation_id:
            print("Reservation ID is missing in the reservation data")
            return {"message": "Reservation ID is missing"}, 400

        # --- Extracción de datos detallada (Usando .get() para evitar KeyErrors) ---
        event = data.get("event", "")
        meta = data.get("meta", {})
        eventId = meta.get("eventId", "")
        messageId = meta.get("messageId", "")

        account_id = reservation_data.get("accountId", "")
        guest_id = reservation_data.get("guestId", "")
        listing_id = reservation_data.get("listingId", "")
        check_in = reservation_data.get("checkIn", "")
        check_out = reservation_data.get("checkOut", "")
        number_of_guests = reservation_data.get("guestsCount", 0)
        platform = reservation_data.get("integration", {}).get("platform", "")
        status = reservation_data.get("status", "")

        guest_data = reservation_data.get("guest", {})
        guest_first_name = guest_data.get("firstName", "")
        guest_last_name = guest_data.get("lastName") or (guest_data.get("fullName", "").split()[-1] if guest_data.get("fullName") else "")

        money_data = reservation_data.get("money", {})
        total_amount = money_data.get("subTotalPrice", 0)
        cleaning_fee = money_data.get("fareCleaning", 0)
        service_fee = money_data.get("hostServiceFee", 0)
        security_deposit = 0 # No disponible directamente en el JSON proporcionado, se mantiene en 0

        listing_data = reservation_data.get("listing", {})
        listing_name = listing_data.get("nickname", "") or listing_data.get("name", "")
        listing_city = listing_data.get("address", {}).get("city", "")

        guest_email = guest_data.get("emails", [""])[0] if guest_data.get("emails") else ""
        guest_phone = guest_data.get("phones", [""])[0] if guest_data.get("phones") else ""

        nights = reservation_data.get("nightsCount", 0)

        # Preparar la fila de datos en el orden de field_names
        row_data = [
            event, eventId, messageId, reservation_id, account_id, guest_id, listing_id,
            check_in, check_out, number_of_guests, platform, status, guest_first_name,
            guest_last_name, total_amount, cleaning_fee, service_fee, security_deposit,
            listing_name, listing_city, guest_email, guest_phone, nights
        ]

        # --- Lógica de búsqueda y actualización/inserción ---
        # Leer todos los valores para encontrar la fila del ID de reserva
        # Aquí usamos la instancia global sheets_service
        result = sheet_instance.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])

        # La primera fila es el encabezado, así que buscamos a partir de la segunda
        # Asumiendo que "reservation_id" es el cuarto elemento (índice 3) en field_names
        reservation_id_col_index = field_names.index("reservation_id") if "reservation_id" in field_names else 3 

        row_index_to_update = None
        for i, row in enumerate(values[1:]): # Iterar desde la segunda fila (índice 1)
            # Asegurarse de que la fila tenga suficientes elementos antes de acceder al índice
            if len(row) > reservation_id_col_index and row[reservation_id_col_index] == str(reservation_id):
                row_index_to_update = i + 2 # +1 para el encabezado, +1 para el índice 0-based
                break

        if row_index_to_update:
            # Actualizar la fila existente
            range_to_update = f"{RANGE_NAME}!A{row_index_to_update}:{chr(64 + len(field_names))}{row_index_to_update}"
            update_body = {"values": [row_data]}
            sheet_instance.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_to_update,
                valueInputOption="RAW",
                body=update_body
            ).execute()
            print(f"✅ Updated row {row_index_to_update} with reservation ID {reservation_id} in Google Sheets")
        else:
            # Añadir una nueva fila
            body = {"values": [row_data]}
            sheet_instance.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME,
                valueInputOption="RAW",
                body=body
            ).execute()
            print(f"✅ Appended new row with reservation ID {reservation_id} to Google Sheets")
        
        return {"message": f"Reserva {reservation_id} procesada exitosamente"}, 200

    except HttpError as error:
        print(f"❌ An error occurred during Google Sheets update: {error}")
        return {"message": f"Error de la API de Google Sheets: {error}"}, 500
    except Exception as e:
        print(f"❌ Error al actualizar Google Sheets: {str(e)}")
        return {"message": f"Fallo al actualizar Google Sheets: {str(e)}"}, 500

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print(f"Webhook recibido: {json.dumps(data, indent=2)}")

    eventType = data.get("event") 
    
    # Adaptar para eventos de Guesty v2
    if eventType not in ["reservation.new", "reservation.updated"]:
        print(f"Evento no procesado: {eventType}")
        return "Evento no procesado", 200

    # Llama a la función de actualización unificada
    return update_google_sheets(data)

if __name__ == "__main__":
    # Render usa gunicorn para ejecutar la app, no este if __name__ == "__main__":
    # Sin embargo, esta sección es útil para pruebas locales si ejecutas python app.py
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
