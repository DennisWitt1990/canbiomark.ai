"""Username + password authentication with server-side sessions.

This replaces the old invite-code/bearer-token scheme entirely:

* credentials are a username and a password, verified against a PBKDF2 hash in
  SQLite;
* a successful login issues an opaque session token that is stored *hashed* in
  ``login_sessions`` and handed to the browser as an HttpOnly cookie;
* logging out, disabling an account or an administrator revoking sessions takes
  effect immediately, because every request looks the session up in SQLite.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..domain.errors import AuthenticationError, ValidationError
from ..domain.login_session import LoginSession
from ..domain.user_account import UserAccount, UserRole
from ..database.repositories.audit_repository import AuditRepository
from ..database.repositories.session_repository import SessionRepository
from ..database.repositories.user_repository import UserRepository
from ..security.password_hasher import PasswordHasher
from ..security.password_policy import PasswordPolicy
from ..security.session_token import SessionTokenFactory

_logger = logging.getLogger(__name__)

_GENERIC_CREDENTIAL_ERROR = "Username or password is incorrect."


@dataclass(frozen=True)
class AuthenticatedSession:
    """The result of a successful login."""

    account: UserAccount
    session: LoginSession
    session_cookie_value: str


class AuthenticationService:
    """Login, logout and session resolution."""

    def __init__(
        self,
        *,
        user_repository: UserRepository,
        session_repository: SessionRepository,
        audit_repository: AuditRepository,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        session_token_factory: SessionTokenFactory,
        session_lifetime_seconds: int,
    ) -> None:
        self._user_repository = user_repository
        self._session_repository = session_repository
        self._audit_repository = audit_repository
        self._password_hasher = password_hasher
        self._password_policy = password_policy
        self._session_token_factory = session_token_factory
        self._session_lifetime_seconds = session_lifetime_seconds

    # -- login / logout -----------------------------------------------------

    def login(
        self, username: str, password: str, client_description: str = ""
    ) -> AuthenticatedSession:
        """Verify credentials and open a session.

        Wrong username and wrong password produce the same error message and,
        as far as practical, the same amount of work, so the endpoint does not
        reveal which usernames exist.
        """
        try:
            normalized_username = UserAccount.normalize_username(username)
        except ValueError as error:
            raise AuthenticationError(_GENERIC_CREDENTIAL_ERROR) from error

        stored_record = self._user_repository.find_by_username(normalized_username)

        if stored_record is None:
            self._perform_dummy_verification(password)
            raise AuthenticationError(_GENERIC_CREDENTIAL_ERROR)

        password_matches = self._password_hasher.verify_password(
            password, stored_record.password_hash
        )
        if not password_matches:
            self._audit_repository.record(
                actor_username=normalized_username,
                action="login.failed",
                subject=normalized_username,
                detail="Wrong password.",
            )
            raise AuthenticationError(_GENERIC_CREDENTIAL_ERROR)

        account = stored_record.account
        account.require_active()

        # Transparently upgrade the stored hash when the cost factor was raised.
        if self._password_hasher.needs_rehash(stored_record.password_hash):
            self._user_repository.update_password(
                account.user_id,
                self._password_hasher.hash_password(password),
                account.must_change_password,
            )

        issued_token = self._session_token_factory.issue()
        session = self._session_repository.create(
            session_id=issued_token.session_id,
            user_id=account.user_id,
            lifetime_seconds=self._session_lifetime_seconds,
            client_description=client_description,
        )
        self._user_repository.record_login(account.user_id)
        self._audit_repository.record(
            actor_username=account.username,
            action="login.succeeded",
            subject=account.username,
        )

        return AuthenticatedSession(
            account=account.with_login_timestamp(),
            session=session,
            session_cookie_value=issued_token.clear_token,
        )

    def logout(self, session_cookie_value: Optional[str]) -> None:
        """Revoke the session behind a cookie value; silently ignores unknown ones."""
        if not session_cookie_value:
            return
        session_id = self._session_token_factory.to_session_id(session_cookie_value)
        self._session_repository.revoke(session_id)

    # -- request-time resolution -------------------------------------------

    def resolve_session(self, session_cookie_value: Optional[str]) -> UserAccount:
        """Map a cookie value to its account, or raise :class:`AuthenticationError`."""
        if not session_cookie_value:
            raise AuthenticationError("You are not signed in.")

        session_id = self._session_token_factory.to_session_id(session_cookie_value)
        session = self._session_repository.find_by_id(session_id)

        if session is None or not session.is_usable():
            raise AuthenticationError("Your session has expired. Please sign in again.")

        account = self._user_repository.find_by_id(session.user_id)
        if account is None:
            self._session_repository.revoke(session_id)
            raise AuthenticationError("Your account no longer exists.")

        account.require_active()
        self._session_repository.touch(session_id)
        return account

    # -- password self service ---------------------------------------------

    def change_own_password(
        self, account: UserAccount, current_password: str, new_password: str
    ) -> None:
        """Let a signed-in user rotate their own password."""
        stored_record = self._user_repository.find_by_username(account.username)
        if stored_record is None:
            raise AuthenticationError("Your account no longer exists.")

        if not self._password_hasher.verify_password(
            current_password, stored_record.password_hash
        ):
            raise AuthenticationError("The current password is incorrect.")

        if current_password == new_password:
            raise ValidationError("The new password must differ from the current one.")

        self._password_policy.validate(new_password)
        self._user_repository.update_password(
            account.user_id,
            self._password_hasher.hash_password(new_password),
            must_change_password=False,
        )
        # Any other session of this user is invalidated after a password change.
        self._session_repository.revoke_all_for_user(account.user_id)
        self._audit_repository.record(
            actor_username=account.username,
            action="password.changed",
            subject=account.username,
        )

    # -- bootstrap ----------------------------------------------------------

    def ensure_administrator_exists(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        quota_bytes: int,
    ) -> Optional[str]:
        """Create the first administrator if no active one exists.

        Returns the password that was set when an account had to be created, so
        the caller can print it once into the server log.  Returns ``None`` when
        an administrator already existed.
        """
        if self._user_repository.count_active_administrators() > 0:
            return None

        existing = self._user_repository.find_by_username(username)
        if existing is not None:
            # Username taken by a non-administrator: promote and reset it.
            generated_password = password or self._password_policy.generate()
            self._user_repository.update_profile(
                existing.account.user_id,
                role=UserRole.ADMINISTRATOR,
                is_active=True,
            )
            self._user_repository.update_password(
                existing.account.user_id,
                self._password_hasher.hash_password(generated_password),
                must_change_password=True,
            )
            _logger.warning(
                "Promoted existing account '%s' to administrator.", username
            )
            return generated_password

        generated_password = password or self._password_policy.generate()
        self._password_policy.validate(generated_password)
        account = self._user_repository.insert(
            username=username,
            display_name=display_name,
            role=UserRole.ADMINISTRATOR,
            password_hash=self._password_hasher.hash_password(generated_password),
            quota_bytes=quota_bytes,
            must_change_password=not password,
        )
        self._audit_repository.record(
            actor_username="system",
            action="user.created",
            subject=account.username,
            detail="Bootstrap administrator.",
        )
        return generated_password

    # -- internals ----------------------------------------------------------

    def _perform_dummy_verification(self, password: str) -> None:
        """Burn roughly one hash worth of CPU so unknown users are not faster."""
        dummy_hash = self._password_hasher.hash_password("unused-placeholder")
        self._password_hasher.verify_password(password, dummy_hash)
