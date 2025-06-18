import base64
import json
import os

# Nombre de tu archivo de credenciales JSON descargado de Google Cloud
# ASEGÚRATE de que este archivo 'credentials.json' esté en la MISMA CARPETA que este script.
CREDENTIALS_FILE = 'credentials.json'

def generate_base64_credentials(file_path):
    try:
        with open(file_path, 'r') as f:
            credentials_json = json.load(f)

        # Convertir el JSON a una cadena y luego codificarla en Base64
        credentials_str = json.dumps(credentials_json)
        base64_bytes = base64.b64encode(credentials_str.encode('utf-8'))
        base64_string = base64_bytes.decode('utf-8')
        return base64_string
    except FileNotFoundError:
        return f"Error: El archivo '{file_path}' no se encontró. Asegúrate de que esté en la misma carpeta."
    except json.JSONDecodeError:
        return f"Error: El archivo '{file_path}' no es un JSON válido."
    except Exception as e:
        return f"Error inesperado: {e}"

if __name__ == "__main__":
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: No se encontró el archivo '{CREDENTIALS_FILE}'.")
        print("Asegúrate de haber descargado 'credentials.json' de Google Cloud y de que esté en la misma carpeta que 'generar_base64.py'.")
    else:
        base64_creds = generate_base64_credentials(CREDENTIALS_FILE)
        if "Error" in base64_creds:
            print(base64_creds)
        else:
            print("--- COPIA ESTA CADENA BASE64 COMPLETA ---")
            print(base64_creds)
            print("--- FIN DE LA CADENA BASE64 ---")
            print("\n¡IMPORTANTE! Copia solo la cadena larga y pégala como el valor de la variable de entorno 'GOOGLE_CREDENTIALS' en Render. SIN COMILLAS, SIN ESPACIOS EXTRA.")