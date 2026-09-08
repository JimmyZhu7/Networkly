"""Conversation ownership on a dedicated, autocommit PostgreSQL session.

Negative single-bigint advisory keys are reserved for assistant conversation
IDs. PostgreSQL keeps these separate from capture's two-integer lock keys.
Closing the session, including process death, releases ownership. Ordinary
request-connection cleanup cannot silently release this dedicated session.
"""

from django.db import connections


BUSY_TEXT = "Another reply is still being prepared in this conversation. Wait for it to finish, then try again."
OWNERSHIP_LOST_TEXT = "This reply was interrupted. Reload the conversation before trying again."


class OwnershipLostError(RuntimeError):
    """The original worker must stop without any more conversation writes."""


class ConversationLock:
    def __init__(self, conversation_id):
        self.conversation_id = int(conversation_id)
        if self.conversation_id <= 0:
            raise ValueError("A saved conversation is required.")
        self.database = None
        self.raw_connection = None
        self.acquired = False

    def __enter__(self):
        source = connections["default"]
        if source.vendor != "postgresql":
            raise RuntimeError("Assistant conversation locking requires PostgreSQL.")
        self.database = source.copy(alias="default")
        # A returned pooled connection can retain session advisory locks.
        # This owner must close a real dedicated session, never return it
        # to a Django connection pool while keeping its lock alive.
        self.database.settings_dict["OPTIONS"] = {
            key: value for key, value in self.database.settings_dict.get("OPTIONS", {}).items()
            if key != "pool"
        }
        try:
            self.database.ensure_connection()
            self.database.set_autocommit(True)
            self.raw_connection = self.database.connection
            with self.database.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [self.lock_key])
                self.acquired = bool(cursor.fetchone()[0])
        except BaseException:
            self.database.close()
            raise
        return self

    @property
    def lock_key(self):
        return -self.conversation_id

    def ensure_owned(self):
        if not self.acquired or self.raw_connection is None or self.raw_connection.closed:
            raise OwnershipLostError(OWNERSHIP_LOST_TEXT)
        # Never reconnect: a new session would not own the original lock.
        try:
            with self.raw_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as exc:
            raise OwnershipLostError(OWNERSHIP_LOST_TEXT) from exc

    def __exit__(self, *exc):
        self.acquired = False
        if self.database is not None:
            self.database.close()
        return False


class AccountGenerationLock(ConversationLock):
    """Positive bigint keys serialize a user's free AI generation, separate from chats.

    Capture uses PostgreSQL's separate two-integer namespace. This lock uses
    a dedicated autocommit session and releases on process death.
    """

    @property
    def lock_key(self):
        return self.conversation_id
