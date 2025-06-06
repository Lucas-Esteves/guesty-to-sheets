# forzar deploy en Render
from flask import Flask, request
import gspread
import json
import os

app = Flask(__name__)

# Configuración de Google Sheets
try:
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS environment variable not set.")
    
    # Intenta cargar las credenciales como JSON directamente
    # Si GOOGLE_CREDENTIALS es una cadena JSON, no necesita json.loads()
    # Si es una ruta a un archivo, se debería leer el archivo
    # Asumimos que GOOGLE_CREDENTIALS contiene el JSON directamente
    gc = gspread.service_account_from_dict(json.loads(credentials_json))
    
    # Reemplaza 'Nombre de tu hoja de cálculo' con el nombre real de tu Google Sheet
    sheet = gc.open("Reservas Guesty").sheet1
except Exception as e:
    print(f"Error al inicializar Google Sheets: {e}")
    # Considera una forma de manejar esto en producción, quizás deteniendo la aplicación
    # o registrando el error de forma más robusta.

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print(f"Webhook recibido: {json.dumps(data, indent=2)}") # Para depuración

    eventType = data.get("eventType")
    if eventType not in ["reservation.new", "reservation.updated"]:
        print(f"Evento no procesado: {eventType}")
        return "Evento no procesado", 200

    # Determinar qué parte del JSON contiene la información de la reserva
    # Guesty a veces usa 'payload' y a veces la información principal está en 'reservation'
    payload = data.get("payload") or data.get("reservation")

    if not payload:
        print("No se encontró 'payload' ni 'reservation' en el webhook.")
        return "Datos de reserva no encontrados", 400

    # Extraer el ID de la reserva para la deduplicación
    reservation_id = payload.get("id") # Guesty usually has an 'id' field for the reservation
    if not reservation_id:
        print("ID de reserva no encontrado en el payload.")
        return "ID de reserva no encontrado", 400

    # Extraer la información de la reserva
    nombre = payload.get("guest", {}).get("fullName", "")
    telefono = payload.get("guest", {}).get("phone", "")
    nacionalidad = payload.get("guest", {}).get("nationality", "")
    plataforma = payload.get("source", "")
    status = payload.get("status", "")
    checkin = payload.get("checkInDate", "")
    checkout = payload.get("checkOutDate", "")
    hora_checkin = payload.get("checkInTime", "")
    hora_checkout = payload.get("checkOutTime", "")
    dias = payload.get("nightsCount", "")
    
    # Algunas veces el listing puede estar directamente en el payload o anidado
    departamento_info = payload.get("listing", {})
    departamento = departamento_info.get("nickname", "") or departamento_info.get("name", "")

    # Manejo de los campos monetarios
    money_info = payload.get("money", {})
    precio = money_info.get("fareAccommodation", "")
    tarifa_limpieza = money_info.get("fareCleaning", "")
    comision = money_info.get("commission", "")
    
    # Si 'commission' no está disponible, podría estar en 'guestCommission' o similar
    if not comision:
        comision = payload.get("guestCommission", "") # Ejemplo, verifica tus payloads reales

    fila = [
        reservation_id, # Añadimos el ID de la reserva para búsqueda
        nombre,
        departamento,
        checkin,
        hora_checkin,
        checkout,
        hora_checkout,
        dias,
        plataforma,
        telefono,
        precio,
        tarifa_limpieza,
        comision,
        status,
        nacionalidad
    ]

    try:
        # Buscar la fila existente por reservation_id
        # Asume que la primera columna de tu hoja es para el reservation_id
        list_of_rows = sheet.get_all_values()
        
        # Encontrar el índice de la columna 'reservation_id'. Esto asume que la primera fila es el encabezado.
        header = list_of_rows[0] if list_of_rows else []
        try:
            reservation_id_col_index = header.index("ID Reserva") # Ajusta el nombre de la columna si es diferente
        except ValueError:
            # Si no se encuentra la columna, asumimos que es la primera columna
            reservation_id_col_index = 0 
            print("Columna 'ID Reserva' no encontrada, asumiendo que el ID de reserva está en la primera columna.")

        # Buscar la fila por el ID de reserva
        row_index_to_update = -1
        for i, row in enumerate(list_of_rows):
            if i == 0: # Saltar la fila del encabezado
                continue
            if row and len(row) > reservation_id_col_index and row[reservation_id_col_index] == str(reservation_id):
                row_index_to_update = i + 1 # gspread usa índices basados en 1
                break

        if row_index_to_update != -1:
            # Actualizar la fila existente
            sheet.update(f'A{row_index_to_update}', [fila])
            print(f"Reserva {reservation_id} actualizada en la fila {row_index_to_update}")
        else:
            # Añadir una nueva fila
            sheet.append_row(fila)
            print(f"Nueva reserva {reservation_id} guardada.")
            
    except Exception as e:
        print(f"Error al escribir en Google Sheets: {e}")
        return "Error interno del servidor", 500

    return "Reserva guardada", 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))