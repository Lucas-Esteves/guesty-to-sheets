import os
import json
import base64
from flask import Flask, request, jsonify, make_response # Importa make_response para la nueva ruta /memdebug
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv # Para cargar variables de entorno en local, si aplica

# --- Importaciones de SQLAlchemy para la Base de Datos ---
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base # Corregido typo en 'declarative_base'
from sqlalchemy.orm import sessionmaker, scoped_session # IMPORTANTE: Se añade scoped_session aquí

# --- Importaciones para el Debug de Memoria ---
import objgraph # <-- NUEVA IMPORTACIÓN PARA LA DEPURACIÓN DE MEMORIA

# Cargar variables de entorno al inicio (esencial para desarrollo local y puede usarse en Render)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURACIÓN GLOBAL DE GOOGLE SHEETS ---
# Estas variables se leerán de las variables de entorno de Render
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1UqW44Uu1r44mDX6_UBn0MSox9cIiW4E6Zmm7xQ9AWm8")
RANGE_NAME = os.getenv("RANGE_NAME", 'test')

# Define el orden de las columnas en tu Google Sheet
# ¡Asegúrate de que tu hoja de cálculo tenga estas columnas y en este orden exacto!
field_names = [
    "event", "eventId", "messageId", "reservation_id", "accountId", "guestId", "listingId",
    "checkIn", "checkOut", "numberOfGuests", "platform", "reservationStatus", "guestFirstName",
    "guestLastName", "totalAmount", "cleaningFee", "serviceFee", "securityDeposit",
    "listing_name", "listing_city", "guest_email", "guest_phone", "nights"
]

# --- INICIALIZACIÓN GLOBAL DEL SERVICIO DE GOOGLE SHEETS ---
# Esta instancia se inicializará una sola vez al arrancar la aplicación.
# Esto es una buena práctica para evitar la recreación costosa en cada solicitud.
sheets_service = None

try:
    google_credentials = os.getenv("GOOGLE_CREDENTIALS")
    if google_credentials is None:
        raise ValueError("La variable de entorno 'GOOGLE_CREDENTIALS' no está configurada.")

    # Decodificar la cadena base64 de las credenciales de la cuenta de servicio
    service_account_info = json.loads(base64.b64decode(google_credentials))
    creds = Credentials.from_service_account_info(service_account_info)
    
    # Construir el servicio de Sheets
    sheets_service = build("sheets", "v4", credentials=creds)
    print("✅ Servicio de Google Sheets inicializado con éxito.")

except Exception as e:
    print(f"❌ ERROR CRÍTICO al inicializar el servicio de Google Sheets: {e}")
    sheets_service = None # Asegurarse de que el servicio no esté disponible si falla la inicialización

# --- CONFIGURACIÓN Y MODELO DE LA BASE DE DATOS SQL (PostgreSQL) ---
# Obtener la URL de conexión a la base de datos de las variables de entorno de Render
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL variable de entorno no configurada. ¡Necesaria para la conexión a la DB!")

Base = declarative_base()

# Definición del modelo de la tabla para el índice de reservas
class ReservationIndex(Base):
    __tablename__ = 'reservation_index' # Nombre de la tabla en tu DB PostgreSQL
    id = Column(Integer, primary_key=True, autoincrement=True) # ID interno de la tabla, autoincremental
    reservation_id = Column(String, unique=True, nullable=False, index=True) # ID de Guesty, debe ser único y se indexa para búsquedas rápidas
    sheet_row_number = Column(Integer, nullable=False) # Número de fila correspondiente en tu Google Sheet

    def __repr__(self):
        return f"<ReservationIndex(reservation_id='{self.reservation_id}', sheet_row_number={self.sheet_row_number})>"

# Crear el motor de la base de datos
engine = create_engine(DATABASE_URL)

# --- CAMBIO CLAVE PARA GESTIÓN DE MEMORIA (SQLAlchemy Session) ---
# Usa scoped_session. Esto asegura que cada "hilo" de trabajo (cada solicitud HTTP)
# obtenga su propia sesión de base de datos y que se gestione de forma segura.
Session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# --- CAMBIO CLAVE PARA GESTIÓN DE MEMORIA (Cierre de SQLAlchemy Session) ---
# Este decorador de Flask asegura que la sesión de la base de datos se elimine
# automáticamente al final de cada solicitud HTTP, liberando recursos de memoria.
@app.teardown_appcontext
def remove_db_session(exception=None):
    Session.remove()
    # print("INFO: SQLAlchemy Session removed for this request.") # Descomentar para depuración si es necesario

# --- Funciones Auxiliares para la Base de Datos (Simplificadas gracias a scoped_session) ---

# Función para asegurar que la tabla 'reservation_index' exista en la DB
# Esta función DEBE llamarse una sola vez al inicio de la aplicación.
def create_db_tables():
    try:
        Base.metadata.create_all(engine)
        print("✅ Tabla 'reservation_index' asegurada en la base de datos.")
    except Exception as e:
        print(f"❌ Error al intentar crear/verificar tabla de la DB: {e}. Esto podría causar problemas.")

# Busca un reservation_id en la base de datos y devuelve su número de fila en Sheets
# Ya no necesitas 'session = Session()' y 'session.close()', scoped_session lo maneja.
def find_reservation_row_in_db(reservation_id):
    try:
        record = Session().query(ReservationIndex).filter_by(reservation_id=str(reservation_id)).first()
        if record:
            return record.sheet_row_number
        return None
    except Exception as e:
        print(f"❌ Error buscando en la DB el ID '{reservation_id}': {e}")
        return None

# Añade un nuevo registro de reserva (ID de Guesty y número de fila de Sheets) a la DB
def add_reservation_to_db(reservation_id, sheet_row_number):
    try:
        new_record = ReservationIndex(reservation_id=str(reservation_id), sheet_row_number=sheet_row_number)
        Session().add(new_record)
        Session().commit() # Importante hacer commit en la misma sesión
        print(f"✅ Reserva {reservation_id} (fila {sheet_row_number}) añadida al índice de la base de datos.")
    except Exception as e:
        Session().rollback() # Si hay un error, deshace la transacción
        print(f"❌ Error añadiendo reserva a la DB '{reservation_id}': {e}")

# Actualiza el número de fila de una reserva existente en la DB
def update_reservation_in_db(reservation_id, new_sheet_row_number):
    try:
        record = Session().query(ReservationIndex).filter_by(reservation_id=str(reservation_id)).first()
        if record:
            record.sheet_row_number = new_sheet_row_number
            Session().commit() # Importante hacer commit en la misma sesión
            print(f"✅ Reserva {reservation_id} actualizada en la base de datos a fila {new_sheet_row_number}.")
        else:
            print(f"⚠️ Reserva {reservation_id} no encontrada en DB para actualizar, añadiendo en su lugar.")
            add_reservation_to_db(reservation_id, new_sheet_row_number)
    except Exception as e:
        Session().rollback()
        print(f"❌ Error actualizando reserva en la DB '{reservation_id}': {e}")

# --- Función para asegurar la fila de encabezado en Google Sheets ---
# Esta función DEBE llamarse una sola vez al inicio de la aplicación para evitar llamadas repetitivas a la API.
def ensure_header_row_exists_global():
    if sheets_service is None:
        print("🚫 Servicio de Google Sheets no inicializado. No se puede verificar/añadir encabezado.")
        raise RuntimeError("Servicio de Google Sheets no disponible.")

    sheet_instance = sheets_service.spreadsheets()

    try:
        # Lee solo la primera fila para verificar el encabezado
        result = sheet_instance.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{RANGE_NAME}!A1:{chr(64 + len(field_names))}1" # Lee el rango exacto del encabezado
        ).execute()
        values = result.get("values", [])

        if not values or values[0] != field_names:
            print("Header row missing or incorrect. Adding/Updating header.")
            body = {"values": [field_names]}
            sheet_instance.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{RANGE_NAME}!A1",
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

# --- Función principal para actualizar Google Sheets (AHORA USANDO LA DB) ---
def update_google_sheets(data):
    if sheets_service == None : 
        print("🚫 Servicio de Google Sheets no inicializado. No se puede actualizar.")
        return {"message": "Server error: Google Sheets service not ready"}, 500

    sheet_instance = sheets_service.spreadsheets()

    try:
        # IMPORTANTE: La llamada a ensure_header_row_exists_global() se ELIMINÓ de aquí.
        # Ahora se ejecuta UNA SOLA VEZ al inicio de la aplicación en el bloque if __name__ == "__main__":

        webhook_topic = data.get("event")
        reservation_data = data.get("reservation", {})

        if not reservation_data:
            print("Reservation data is missing in the request")
            return {"message": "Reservation data is missing"}, 400

        reservation_id = reservation_data.get("_id")
        if not reservation_id:
            print("Reservation ID is missing in the reservation data")
            return {"message": "Reservation ID is missing"}, 400

        # --- Extracción de datos detallada desde el webhook de Guesty ---
        # Asegúrate de que el orden de estos campos coincida exactamente con 'field_names'
        # y las columnas en tu Google Sheet.
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
        # guest_last_name: intenta obtenerlo directamente, si no, del fullName.
        guest_last_name = guest_data.get("lastName") or (guest_data.get("fullName", "").split()[-1] if guest_data.get("fullName") else "")

        money_data = reservation_data.get("money", {})
        total_amount = money_data.get("subTotalPrice", 0)
        cleaning_fee = money_data.get("fareCleaning", 0)
        service_fee = money_data.get("hostServiceFee", 0)
        security_deposit = 0 # Mantener en 0 si no se extrae de Guesty

        listing_data = reservation_data.get("listing", {})
        listing_name = listing_data.get("nickname", "") or listing_data.get("name", "")
        listing_city = listing_data.get("address", {}).get("city", "")

        guest_email = guest_data.get("emails", [""])[0] if guest_data.get("emails") else ""
        guest_phone = guest_data.get("phones", [""])[0] if guest_data.get("phones") else ""

        nights = reservation_data.get("nightsCount", 0)

        # Preparar la fila de datos en el ORDEN DEFINIDO por 'field_names'
        row_data = [
            event, eventId, messageId, reservation_id, account_id, guest_id, listing_id,
            check_in, check_out, number_of_guests, platform, status, guest_first_name,
            guest_last_name, total_amount, cleaning_fee, service_fee, security_deposit,
            listing_name, listing_city, guest_email, guest_phone, nights
        ]

        # --- Lógica de BÚSQUEDA en la Base de Datos AUXILIAR (¡RÁPIDA!) ---
        row_index_to_update = find_reservation_row_in_db(reservation_id)

        # --- Lógica CONDICIONAL de acción basada en si se encontró y el 'topic' del webhook ---
        if row_index_to_update:
            # CASO 1: La reserva YA EXISTE en nuestra base de datos (y, por lo tanto, en Google Sheets)
            # Siempre la actualizamos en Google Sheets, sin importar el topic.
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
            # CASO 2: La reserva NO SE ENCONTRÓ en nuestra base de datos auxiliar.
            # Aquí el 'topic' del webhook es CRUCIAL para evitar duplicados de reservas antiguas.
            if webhook_topic == "reservation.new":
                # Si es una reserva GENUINAMENTE NUEVA, la agregamos a Sheets Y a nuestra DB auxiliar.
                body = {"values": [row_data]}
                append_result = sheet_instance.values().append(
                    spreadsheetId=SPREADSHEET_ID,
                    range=RANGE_NAME, # Append agrega al final de la hoja activa
                    valueInputOption="RAW",
                    body=body
                ).execute()
                
                # Obtener el número de fila en el que Google Sheets insertó la reserva
                updated_range = append_result.get('updates', {}).get('updatedRange', '')
                if updated_range:
                    try:
                        # Ejemplo: "Hoja1!A123:W123" -> extraer "123"
                        sheet_row_number_appended = int(updated_range.split('!')[1].split(':')[0].strip('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
                        add_reservation_to_db(reservation_id, sheet_row_number_appended) # ¡Añade el ID y la fila a tu índice de DB!
                        print(f"✅ Appended new row with reservation ID {reservation_id} to Google Sheets (row {sheet_row_number_appended}) AND added to DB index.")
                    except (ValueError, IndexError) as e:
                        print(f"❌ Error al parsear el número de fila de updatedRange '{updated_range}': {e}. No se pudo indexar en la DB.")
                        print(f"✅ Appended new row with reservation ID {reservation_id} to Google Sheets (DB index update failed).")
                else:
                    print(f"✅ Appended new row with reservation ID {reservation_id} to Google Sheets, but could not determine new row number for DB index. Manual sync might be needed later.")

            elif webhook_topic == "reservation.updated":
                # Si es una ACTUALIZACIÓN de una reserva que NO encontramos en nuestra DB:
                # Esto significa que es una reserva "vieja" (existía en Guesty antes de que empezaras a usar este sistema/Excel).
                # La IGNORAMOS para evitar duplicados no deseados en tu hoja.
                print(f"⚠️ Received 'reservation.updated' for ID {reservation_id} which was not found in DB/Sheets. Ignoring to prevent duplicates of old reservations.")
                # Se devuelve un 200 OK porque el webhook fue procesado intencionalmente (ignorando la acción de añadir).
                return {"message": f"Reserva {reservation_id} (updated) no encontrada en la hoja, ignorada para evitar duplicados."}, 200

            else:
                # Otros tipos de topic de webhook que no quieres manejar para añadir/actualizar
                print(f"ℹ️ Received webhook with unexpected topic '{webhook_topic}' for ID {reservation_id}. Ignoring.")
                return {"message": f"Webhook topic '{webhook_topic}' for ID {reservation_id} ignored."}, 200

        return {"message": f"Reserva {reservation_id} procesada exitosamente"}, 200

    except HttpError as error:
        print(f"❌ An error occurred during Google Sheets update: {error}")
        return {"message": f"Error de la API de Google Sheets: {error}"}, 500
    except Exception as e:
        print(f"❌ Error al actualizar Google Sheets: {str(e)}")
        return {"message": f"Fallo al actualizar Google Sheets: {str(e)}"}, 500

# --- Ruta del Webhook de Flask ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print(f"Webhook recibido: {json.dumps(data, indent=2)}")

    webhook_event_type = data.get("event") 
    
    # Verifica que el evento sea de un tipo que queremos procesar para reservas
    if webhook_event_type not in ["reservation.new", "reservation.updated"]:
        print(f"Evento no procesado: {webhook_event_type}. Solo procesamos 'reservation.new' y 'reservation.updated'.")
        return jsonify({"message": f"Evento '{webhook_event_type}' no procesado"}), 200

    # Llama a la función de actualización unificada
    return update_google_sheets(data)

# --- NUEVA RUTA: La "Puerta Secreta" para depuración de memoria ---
# Accede a esta ruta en tu navegador (ej. https://tu-app-en-render.onrender.com/memdebug)
# para ver el uso de memoria en tiempo real.
@app.route("/memdebug")
def memdebug():
    try:
        # Genera una lista de los 50 tipos de objetos más comunes en memoria
        # 'file=None' hace que retorne la lista en lugar de imprimirla.
        top_objects = objgraph.show_most_common_types(limit=50, file=None)
        
        # --- CORRECCIÓN AQUÍ ---
        output = ["<!DOCTYPE html><html><head><title>Memoria de la App</title></head><body><h1>Top 50 objetos en memoria:</h1>", "<pre>"]
        
        if top_objects is None:
            output.append("objgraph.show_most_common_types devolvió 'None'. Esto podría indicar un problema de entorno o acceso a la memoria.")
        elif not top_objects: # Maneja el caso de lista vacía
            output.append("objgraph no encontró objetos o la lista está vacía.")
        else:
            for obj_type, count in top_objects:
                output.append(f"{obj_type}: {count}")
        
        output.append("</pre></body></html>")

        response = make_response("".join(output))
        response.headers["Content-Type"] = "text/html"
        return response
    except Exception as e:
        return f"Error al generar el informe de memoria: {e}", 500

# --- Punto de entrada principal para Flask ---
if __name__ == "__main__":
    # Importante: `create_db_tables()` y `ensure_header_row_exists_global()`
    # DEBEN llamarse UNA SOLA VEZ al iniciar la app.
    # En Render, Gunicorn (o tu WSGI server) ejecutará tu aplicación.
    # Esta sección 'if __name__ == "__main__":' es principalmente para cuando ejecutas
    # el script directamente (python app.py) y para pruebas locales.
    
    create_db_tables() # Llama a esta función para asegurar que la tabla de la DB exista

    # --- CAMBIO CLAVE AQUÍ: Llamar a ensure_header_row_exists_global UNA SOLA VEZ ---
    # Esto evita llamadas repetitivas a la API de Google Sheets en cada webhook.
    try:
        ensure_header_row_exists_global() 
    except Exception as e:
        print(f"FATAL ERROR: Could not ensure Google Sheets header row: {e}")
        import sys
        sys.exit(1) # Termina la aplicación si el encabezado no se puede establecer

    port = int(os.environ.get("PORT", 5000))
    # Para desarrollo local, puedes activar debug=True
    app.run(debug=os.environ.get("FLASK_DEBUG", "False") == "True", host="0.0.0.0", port=port)

