@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("eventType") not in ["reservation.new", "reservation.updated"]:
        return "Evento no procesado", 200

    # Extraer correctamente el payload de la reserva
    reserva = data.get("reservation")
    if not reserva or not isinstance(reserva, dict) or not reserva.get("guest"):
        reserva = data.get("payload")

    if not reserva or not isinstance(reserva, dict) or not reserva.get("guest"):
        print("❌ No se encontró información válida de la reserva")
        return "Datos inválidos", 400

    # Extraer los campos
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

    # Campos financieros
    money = reserva.get("money", {})
    precio = money.get("fareAccommodation", "")
    tarifa_limpieza = money.get("fareCleaning", "")
    comision = money.get("commission", "")

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

    try:
        sheet.append_row(fila)
        print("✅ Fila guardada en Sheets:", fila)
        return "Reserva guardada", 200
    except Exception as e:
        print("❌ Error al guardar en Sheets:", str(e))
        return "Error al guardar", 500
