import os
import sys
import smtplib
import time
import requests
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Lee el archivo .env y carga sus variables
load_dotenv()

# Configuración que viene del .env
Token = os.getenv("Token")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def preguntar_siguiente_accion() -> None:
    """
    Pregunta al usuario si desea regresar al menú principal o salir del programa.
    """
    print("\n------------------------------------------")
    print("¿Qué le gustaría hacer ahora?")
    print("1. Volver al menú principal")
    print("2. Cerrar el programa")
    print("------------------------------------------")

    opcion = input("Elija una opción (1 o 2): ").strip()
    if opcion == "2":
        salir_programa()
    # Con "1" (o enter) solo se regresa y el menú vuelve a mostrarse.


def consultar_banxico_serie() -> None:
    """
    Solicita dinámicamente cualquier clave de serie al usuario
    y realiza la consulta HTTP en tiempo real a Banxico.
    """
    if not Token:
        print("\n[x] Error. No se encontró Token en el archivo .env")
        preguntar_siguiente_accion()
        return

    serie = input("\nEscriba la clave de la serie de Banxico (Por ejemplo. SF61745, SP68257, etc): ").strip()

    if not serie:
        print("[x] Error. Debe ingresar una clave de serie válida.")
        preguntar_siguiente_accion()
        return

    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{serie}/datos/oportuno"
    headers = {"Bmx-Token": Token}

    try:
        print(f"\nConsultando la serie '{serie}' en Banxico...")
        response = requests.get(url, headers=headers, timeout=10)

        # Revisar que la petición HTTP haya salido bien
        if response.status_code == 200:
            datos = response.json()
            print("\nConexión exitosa a Banxico.")

            series_list = datos.get("bmx", {}).get("series", [])
            if series_list:
                info_serie = series_list[0]
                titulo = info_serie.get("titulo", "Sin título")
                observaciones = info_serie.get("datos", [])

                print("\n------------------------------------------")
                print(f"Serie   : {serie}")
                print(f"Nombre  : {titulo}")
                if observaciones:
                    print(f"Fecha   : {observaciones[0].get('fecha')}")
                    print(f"Valor   : {observaciones[0].get('dato')}")
                else:
                    print("[x] No se encontraron observaciones para esta serie.")
                print("------------------------------------------")
            else:
                print("Respuesta recibida:", datos)
        else:
            print(f"\n[x] Error de conectividad/serie no encontrada. Código HTTP: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"\n[x] Error al conectar con el servidor de Banxico: {e}")

    # Esperar la decisión del usuario antes de volver al menú
    preguntar_siguiente_accion()


def enviar_correo(destinatario: str, asunto: str, cuerpo: str) -> bool:
    """
    Envía un correo electrónico utilizando la configuración SMTP (.env).
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("\n[x] Error. Faltan credenciales SMTP_USER o SMTP_PASSWORD en el .env")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = destinatario
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo, 'plain'))

        print("\nConectando al servidor SMTP...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)

        server.send_message(msg)
        server.quit()
        print("Correo enviado de manera correcta")
        return True

    except Exception as e:
        print(f"[x] Error al enviar el correo: {e}")
        return False


def calcular_isc() -> None:
    """
    Consulta automáticamente la tasa actual semanal de CETES (Serie SF43936) en Banxico,
    pide al usuario el monto y las semanas de inversión, calcula el interés,
    genera un reporte y lo envía por correo.
    """
    if not Token:
        print("\n[x] Error. No se encontró Token en el archivo .env")
        preguntar_siguiente_accion()
        return

    # 1: obtener la tasa vigente de CETES a 28 días (serie SF43936)
    serie_cetes = "SF43936"
    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{serie_cetes}/datos/oportuno"
    headers = {"Bmx-Token": Token}

    tasa_anual = 0.06  # Tasa que se usa si falla la consulta a Banxico
    try:
        print("\nConsultando la tasa actual semanal de CETES en Banxico...")
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            datos = response.json()
            series_list = datos.get("bmx", {}).get("series", [])
            if series_list:
                observaciones = series_list[0].get("datos", [])
                if observaciones:
                    tasa_str = observaciones[0].get("dato")
                    tasa_anual = float(tasa_str) / 100
                    print(f"[+] Tasa de CETES encontrada ({observaciones[0].get('fecha')}): {tasa_str}% anual")
        else:
            print(f"[x] No se pudo conectar con Banxico (Código {response.status_code}). Usando tasa estándar de 6.0%.")
    except Exception as e:
        print(f"[x] Error al consultar la tasa de CETES: {e}. Usando tasa estándar de 6.0%.")

    # Paso 2: pedir el monto y las semanas
    try:
        print("\n--- Calculadora de interés CETES (ISC) ---")
        monto = float(input("¿Cuánto dinero desea invertir? ($): "))

        print("\nAlgunas referencias para ingresar el plazo:")
        print("  3 meses  : 13 semanas")
        print("  6 meses  : 26 semanas")
        print("  12 meses : 52 semanas")
        semanas = int(input("¿Cuántas semanas mantendrá su inversión?: "))

        if monto <= 0 or semanas <= 0:
            print("[x] Error. El monto y las semanas deben ser mayores a cero.")
            preguntar_siguiente_accion()
            return

        # Paso 3: calcular el interés (semanas a días, año comercial de 360 días)
        dias = semanas * 7
        interes = monto * tasa_anual * (dias / 360)
        monto_total = monto + interes

        reporte = (
            f"********** Reporte ISC (CETES) **********\n"
            f"Tasa CETES usada    : {tasa_anual * 100:.2f}% anual\n"
            f"Capital invertido   : ${monto:,.2f}\n"
            f"Plazo               : {semanas} semana(s) ({dias} días)\n"
            f"Interés generado    : ${interes:,.2f}\n"
            f"-----------------------------------------\n"
            f"Total final         : ${monto_total:,.2f}\n"
            f"*****************************************"
        )
        #Se nos indicó que el reporte solamente debe llegar por correo, sin embargo, para obtener en terminal: print(f"\n{reporte}")

        correo_destino = input("\nEscriba el correo donde quiere recibir el reporte: ").strip()

        print("\nProcesando su reporte...")
        time.sleep(2)  # Pequeña pausa mientras se arma el reporte

        if correo_destino:
            enviar_correo(
                destinatario=correo_destino,
                asunto="Reporte. Cálculo de Interés CETES (ISC)",
                cuerpo=reporte
            )

    except ValueError:
        print("\n[x] Error. Ingrese únicamente números válidos.")
    except Exception as e:
        print(f"[x] Error en el cálculo: {e}")

    # Esperar la decisión del usuario antes de volver al menú
    preguntar_siguiente_accion()


def salir_programa() -> None:
    """
    Finaliza la ejecución del programa con una cuenta regresiva de puntitos
    (3, 2 y 1 puntos), uno cada medio segundo.
    """
    print("\nSaliendo del programa...")
    time.sleep(0.75)
    print("...")
    time.sleep(0.75)
    print("..")
    time.sleep(0.75)
    print(".")
    time.sleep(0.75)
    print("Programa finalizado")
    sys.exit()


def mostrar_menu() -> None:
    """
    Despliega el menú principal e interactúa iterativamente con el usuario.
    """
    while True:
        print("\n******************************************")
        print("             Menú principal               ")
        print("******************************************")
        print("1. Consultar serie de Banxico")
        print("2. Calcular interés con CETES")
        print("3. Cerrar el programa")
        print("******************************************")

        try:
            opcion = input("Elija una opción: ").strip()

            if opcion == "1":
                consultar_banxico_serie()
            elif opcion == "2":
                calcular_isc()
            elif opcion == "3":
                salir_programa()
            else:
                print("\n[x] Opción no válida. Por favor teclee 1, 2 o 3.")

        except KeyboardInterrupt:
            print("\n\n[x] Interrupción del sistema detectada.")
            salir_programa()
        except Exception as e:
            print(f"\n[x] Error inesperado: {e}")

if __name__ == "__main__":
    mostrar_menu()