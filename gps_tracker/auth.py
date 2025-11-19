"""
Funciones de autenticación y generación de tokens.

Proporciona utilidades para hashear contraseñas y crear tokens JWT
para la autenticación de usuarios. Utiliza passlib para gestionar los
hashes y python-jose para firmar tokens.
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

# Clave secreta para firmar los tokens. En producción, obtener de variables de entorno.
SECRET_KEY = "change-this-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica que una contraseña en texto claro coincide con su hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera el hash de una contraseña."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crea un token JWT con una expiración opcional."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
