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


# Abrir la hoja de cálculo (cambiá el nombre si tu planilla tiene otro)
sheet = client.open("Prueba").sheet1

@app.route("/", methods=["GET"])
def home():
    return "Running OK"

#@app.route("/webhook", methods=["POST"])
#def webhook():
 #   data = request.json
#
 #   reserva_id = data.get("id")
  #  nombre = data.get("guest", {}).get("fullName", "")
   # email = data.get("guest", {}).get("email", "")
    #checkin = data.get("checkInDate", "")
    #checkout = data.get("checkOutDate", "")
    #creado = data.get("createdAt", datetime.datetime.now().isoformat())

    #sheet.append_row([reserva_id, nombre, email, checkin, checkout, creado])

    #return "Reserva guardada", 200
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    # Filtrar eventos que no sean de reserva
    if data.get("eventType") not in ["reservation.new", "reservation.updated"]:
        return "Evento no procesado", 200

    reserva = data.get("payload", {})

    nombre = reserva.get("guest", {}).get("fullName", "")
    telefono = reserva.get("guest", {}).get("phone", "")
    nacionalidad = reserva.get("guest", {}).get("nationality", "")
    plataforma = reserva.get("source", "")
    status = reserva.get("status", "")
    checkin = reserva.get("checkInDate", "")
    checkout = reserva.get("checkOutDate", "")
    hora_checkin = reserva.get("checkInTime", "")
    hora_checkout = reserva.get("checkOutTime", "")
    dias = reserva.get("nightsCount", "")
    departamento = reserva.get("listing", {}).get("nickname", "")
    
    precio = reserva.get("financials", {}).get("grossAmount", {}).get("amount", "")
    tarifa_limpieza = reserva.get("financials", {}).get("cleaningFee", {}).get("amount", "")
    comision = reserva.get("financials", {}).get("platformCommission", {}).get("amount", "")

    fila = [
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

    sheet.append_row(fila)
    return "Reserva guardada", 200




if __name__ == "__main__":
    print("Iniciando servidor...")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


