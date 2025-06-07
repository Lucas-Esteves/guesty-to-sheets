import os
import json
import base64
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)

# --- Configuración de Google Sheets (Adaptado de FastAPI) ---
# Reemplaza con tu Google Sheet ID y el nombre de la pestaña
SPREADSHEET_ID = "1UqW44Uu1r44mDX6_UBn0MSox9cIiW4E6Zmm7xQ9AWm8"
RANGE_NAME = 'test'

# Define el orden de las columnas en tu Google Sheet
# ¡Asegúrate de que tu hoja de cálculo tenga estas columnas y en este orden!
field_names = [
    "event", "eventId", "messageId", "reservation_id", "accountId", "guestId", "listingId",
    "checkIn", "checkOut", "numberOfGuests", "platform", "reservationStatus", "guestFirstName",
    "guestLastName", "totalAmount", "cleaningFee", "serviceFee", "securityDeposit",
    "listing_name", "listing_city", "guest_email", "guest_phone", "nights"
]

# --- Funciones de Google Sheets (Adaptadas de FastAPI) ---

def get_google_sheets_service():
    google_credentials = os.getenv("GOOGLE_CREDENTIALS")

    if google_credentials is None:
        raise ValueError("La variable de entorno 'GOOGLE_CREDENTIALS' no está configurada.")

    try:
        # Decodificar la cadena base64 de las credenciales
        service_account_info = json.loads(base64.b64decode(google_credentials))
        creds = Credentials.from_service_account_info(service_account_info)
        # Usar googleapiclient para el servicio, ya que gspread no permite update por rango dinámico fácilmente
        service = build("sheets", "v4", credentials=creds)
        return service
    except Exception as e:
        print(f"Error al cargar las credenciales de Google Sheets: {e}")
        raise

def ensure_header_row_exists():
    service = get_google_sheets_service()
    sheet_service = service.spreadsheets()

    try:
        result = sheet_service.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])

        if not values or values[0] != field_names: # Comprueba si no hay valores o si el encabezado no coincide
            print("Header row missing or incorrect. Adding/Updating header.")
            body = {"values": [field_names]}
            sheet_service.values().update(
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

def update_google_sheets(data):
    try:
        service = get_google_sheets_service()
        sheet_service = service.spreadsheets()

        # Asegurar que la fila de encabezado exista antes de procesar datos
        ensure_header_row_exists()

        reservation_data = data.get("reservation", {})
        if not reservation_data:
            print("Reservation data is missing in the request")
            return {"message": "Reservation data is missing"}, 400

        reservation_id = reservation_data.get("_id")
        if not reservation_id:
            print("Reservation ID is missing in the reservation data")
            return {"message": "Reservation ID is missing"}, 400

        # --- Extracción de datos detallada (Adaptada de FastAPI) ---
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

        # --- Lógica de búsqueda y actualización/inserción (Adaptada de FastAPI) ---
        # Leer todos los valores para encontrar la fila del ID de reserva
        result = sheet_service.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])

        # La primera fila es el encabezado, así que buscamos a partir de la segunda
        # Asumiendo que "reservation_id" es el cuarto elemento (índice 3) en field_names
        reservation_id_col_index = field_names.index("reservation_id") if "reservation_id" in field_names else 3 # Default to 3 if not found

        row_index_to_update = None
        for i, row in enumerate(values[1:]): # Iterar desde la segunda fila (índice 1)
            if len(row) > reservation_id_col_index and row[reservation_id_col_index] == str(reservation_id):
                row_index_to_update = i + 2 # +1 para el encabezado, +1 para el índice 0-based
                break

        if row_index_to_update:
            # Actualizar la fila existente
            range_to_update = f"{RANGE_NAME}!A{row_index_to_update}:{chr(64 + len(field_names))}{row_index_to_update}"
            update_body = {"values": [row_data]}
            sheet_service.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_to_update,
                valueInputOption="RAW",
                body=update_body
            ).execute()
            print(f"✅ Updated row {row_index_to_update} with reservation ID {reservation_id} in Google Sheets")
        else:
            # Añadir una nueva fila
            body = {"values": [row_data]}
            sheet_service.values().append(
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

    eventType = data.get("event") # Guesty v2 webhook usa "event" en lugar de "eventType"
    
    # Adaptar para eventos de Guesty v2
    if eventType not in ["reservation.new", "reservation.updated"]:
        print(f"Evento no procesado: {eventType}")
        return "Evento no procesado", 200

    # Llama a la función de actualización unificada
    return update_google_sheets(data)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

    