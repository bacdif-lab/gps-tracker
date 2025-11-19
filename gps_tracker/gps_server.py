"""
Servidor básico de ingestión de datos GPS.

Este módulo implementa un servidor TCP que escucha en un puerto configurable y
recibe mensajes de dispositivos GPS. Los mensajes se esperan en formato
`<device_id>,<latitud>,<longitud>,<velocidad>,<rumbo>`. Al recibir un mensaje
válido, el servidor guarda la posición en la base de datos.

En un escenario real, los dispositivos GPS utilizan protocolos específicos
como GT06, TK103, etc. Estos protocolos definen campos binarios o ASCII que
incluyen información adicional. Para integrar un dispositivo concreto, se
necesitaría implementar un decodificador acorde a su protocolo. Este
servidor es meramente demostrativo para simular el flujo de datos.

El servidor se ejecuta de forma asíncrona usando asyncio.
"""

import asyncio
import logging
from typing import Optional

from .database import init_db, save_position


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GPSServer:
    """Servidor TCP para recibir datos GPS."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5000) -> None:
        self.host = host
        self.port = port

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("Conexión entrante de %s", addr)
        while True:
            data = await reader.readline()
            if not data:
                logger.info("Conexión cerrada por %s", addr)
                break
            message = data.decode().strip()
            logger.debug("Datos recibidos: %s", message)
            # Procesar el mensaje
            try:
                device_id, lat_str, lon_str, *rest = message.split(",")
                latitude = float(lat_str)
                longitude = float(lon_str)
                speed: Optional[float] = None
                course: Optional[float] = None
                if rest:
                    # La velocidad puede ser proporcionada (rest[0])
                    try:
                        speed = float(rest[0]) if rest[0] else None
                    except ValueError:
                        speed = None
                if len(rest) > 1:
                    try:
                        course = float(rest[1]) if rest[1] else None
                    except ValueError:
                        course = None
                save_position(device_id, latitude, longitude, speed, course)
                logger.info(
                    "Posición guardada de %s: lat=%s, lon=%s, speed=%s, course=%s",
                    device_id,
                    latitude,
                    longitude,
                    speed,
                    course,
                )
            except Exception as exc:
                logger.error("Error procesando mensaje %s: %s", message, exc)
        writer.close()
        await writer.wait_closed()

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addr = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        logger.info("Servidor de GPS escuchando en %s", addr)
        async with server:
            await server.serve_forever()


def main() -> None:
    """Punto de entrada cuando se ejecuta el módulo directamente."""
    init_db()
    server = GPSServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Servidor detenido por el usuario")


if __name__ == "__main__":
    main()
