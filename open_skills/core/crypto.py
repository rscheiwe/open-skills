"""
Cryptographic utilities for secure secret storage.
Uses JWT for encrypting sensitive values.
"""

from typing import Optional

from jose import jwt, JWTError

from open_skills.config import settings
from open_skills.core.exceptions import AuthenticationError


def encrypt_value(value: str, secret: Optional[str] = None) -> str:
    """
    Encrypt a value using JWT signing.

    Args:
        value: The value to encrypt
        secret: Optional secret key (defaults to settings.jwt_secret)

    Returns:
        Encrypted token string

    Raises:
        AuthenticationError: If encryption fails
    """
    secret_key = secret or settings.jwt_secret
    try:
        token = jwt.encode(
            {"v": value},
            secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return token
    except Exception as e:
        raise AuthenticationError(f"Failed to encrypt value: {e}")


def decrypt_value(token: str, secret: Optional[str] = None) -> str:
    """
    Decrypt a JWT token to retrieve the original value.

    Args:
        token: The encrypted token
        secret: Optional secret key (defaults to settings.jwt_secret)

    Returns:
        Decrypted value

    Raises:
        AuthenticationError: If decryption fails or token is invalid
    """
    secret_key = secret or settings.jwt_secret
    try:
        data = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return data["v"]
    except JWTError as e:
        raise AuthenticationError(f"Failed to decrypt value: {e}")
    except KeyError:
        raise AuthenticationError("Invalid token format: missing 'v' key")


def encrypt_dict(data: dict, secret: Optional[str] = None) -> str:
    """
    Encrypt a dictionary as a JWT token.

    Args:
        data: Dictionary to encrypt
        secret: Optional secret key (defaults to settings.jwt_secret)

    Returns:
        Encrypted token string

    Raises:
        AuthenticationError: If encryption fails
    """
    secret_key = secret or settings.jwt_secret
    try:
        token = jwt.encode(
            data,
            secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return token
    except Exception as e:
        raise AuthenticationError(f"Failed to encrypt dict: {e}")


def decrypt_dict(token: str, secret: Optional[str] = None) -> dict:
    """
    Decrypt a JWT token to retrieve a dictionary.

    Args:
        token: The encrypted token
        secret: Optional secret key (defaults to settings.jwt_secret)

    Returns:
        Decrypted dictionary

    Raises:
        AuthenticationError: If decryption fails or token is invalid
    """
    secret_key = secret or settings.jwt_secret
    try:
        data = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return data
    except JWTError as e:
        raise AuthenticationError(f"Failed to decrypt dict: {e}")


def verify_token(token: str, secret: Optional[str] = None) -> bool:
    """
    Verify if a token is valid without decrypting it.

    Args:
        token: The token to verify
        secret: Optional secret key (defaults to settings.jwt_secret)

    Returns:
        True if valid, False otherwise
    """
    try:
        decrypt_dict(token, secret)
        return True
    except AuthenticationError:
        return False
