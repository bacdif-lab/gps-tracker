from fastapi import Request, HTTPException, status
from time import time

# Almacenamiento en memoria temporal para intentos por IP
login_attempts = {}
MAX_ATTEMPTS = 5
BLOCK_TIME = 300  # 5 minutos


async def limit_login_attempts(request: Request):
    client_ip = request.client.host
    current_time = time()
    attempts = login_attempts.get(client_ip, {"count": 0, "time": 0})

    if attempts["count"] >= MAX_ATTEMPTS and current_time - attempts["time"] < BLOCK_TIME:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Intente más tarde."
        )

    if current_time - attempts["time"] > BLOCK_TIME:
        login_attempts[client_ip] = {"count": 1, "time": current_time}
    else:
        login_attempts[client_ip]["count"] += 1
        login_attempts[client_ip]["time"] = current_time

    return True
