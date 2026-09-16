"""Minimum quality requirements for user-chosen passwords."""
from __future__ import annotations

import secrets
import string

from ..domain.errors import PasswordPolicyError

_GENERATED_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_=+"


class PasswordPolicy:
    """Validates passwords and generates compliant random ones."""

    def __init__(self, minimum_length: int = 10) -> None:
        self._minimum_length = max(8, minimum_length)

    @property
    def minimum_length(self) -> int:
        return self._minimum_length

    def describe(self) -> str:
        return (
            f"At least {self._minimum_length} characters, including one letter "
            f"and one digit."
        )

    def validate(self, plain_password: str) -> None:
        """Raise :class:`PasswordPolicyError` when the password is too weak."""
        password = plain_password or ""

        if len(password) < self._minimum_length:
            raise PasswordPolicyError(
                f"The password must contain at least {self._minimum_length} characters."
            )
        if password.strip() != password:
            raise PasswordPolicyError(
                "The password must not start or end with whitespace."
            )
        if not any(character.isalpha() for character in password):
            raise PasswordPolicyError("The password must contain at least one letter.")
        if not any(character.isdigit() for character in password):
            raise PasswordPolicyError("The password must contain at least one digit.")

    def generate(self) -> str:
        """Generate a random password that satisfies :meth:`validate`."""
        while True:
            candidate = "".join(
                secrets.choice(_GENERATED_PASSWORD_ALPHABET)
                for _ in range(max(16, self._minimum_length))
            )
            try:
                self.validate(candidate)
            except PasswordPolicyError:
                continue
            return candidate
