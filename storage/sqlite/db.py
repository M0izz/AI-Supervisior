import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional
import aiosqlite

logger = logging.getLogger("supervisor.storage.sqlite")

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


class DatabaseManager:
    """
    Manages SQLite database connections with WAL mode and foreign key enforcement.
    Serves as the local-first persistent source of truth for AI Supervisor.
    """

    def __init__(self, db_path: str = "supervisor.db"):
        self.db_path = Path(db_path).resolve()
        self._initialized = False
        self._lock = asyncio.Lock()

    async def init_db(self) -> None:
        """
        Initializes the SQLite database, enabling WAL mode, enforcing foreign keys,
        and executing the schema DDL if tables do not exist.
        """
        async with self._lock:
            if self._initialized:
                return

            # Ensure parent directories exist
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiosqlite.connect(self.db_path) as db:
                # Enable WAL mode and foreign keys
                await db.execute("PRAGMA journal_mode = WAL;")
                await db.execute("PRAGMA foreign_keys = ON;")
                await db.execute("PRAGMA synchronous = NORMAL;")
                await db.execute("PRAGMA busy_timeout = 5000;")

                # Read and execute schema
                if SCHEMA_FILE.exists():
                    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
                    # Migration: ensure memory_records has Phase 7+ columns if created by earlier versions
                    try:
                        cursor = await db.execute("PRAGMA table_info(memory_records);")
                        existing_cols = [c[1] for c in await cursor.fetchall()]
                        if existing_cols and "project_id" not in existing_cols:
                            additions = [
                                ("project_id", "TEXT DEFAULT ''"),
                                ("memory_type", "TEXT DEFAULT 'FACT'"),
                                ("status", "TEXT DEFAULT 'OBSERVED'"),
                                ("confidence", "REAL DEFAULT 1.0"),
                                ("source", "TEXT DEFAULT 'system'"),
                                ("source_id", "TEXT DEFAULT ''"),
                                ("created_by", "TEXT DEFAULT 'system'"),
                                ("superseded_by", "TEXT"),
                                ("updated_at", "TEXT")
                            ]
                            for col_name, col_def in additions:
                                if col_name not in existing_cols:
                                    await db.execute(f"ALTER TABLE memory_records ADD COLUMN {col_name} {col_def};")
                            await db.commit()
                    except Exception as me:
                        logger.debug(f"Migration check completed: {me}")

                    await db.executescript(schema_sql)
                    await db.commit()
                else:
                    raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE}")

            self._initialized = True
            logger.info(f"SQLite WAL database initialized at {self.db_path}")

    async def is_wal_mode(self) -> bool:
        """Check if WAL journal mode is active."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("PRAGMA journal_mode;")
            row = await cursor.fetchone()
            if row:
                return str(row[0]).strip().lower() == "wal"
            return False

    async def is_foreign_keys_enabled(self) -> bool:
        """Check if foreign key constraints are enabled on managed connections."""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute("PRAGMA foreign_keys;")
            row = await cursor.fetchone()
            if row:
                return int(row[0]) == 1
            return False
        finally:
            await conn.close()

    async def get_connection(self) -> aiosqlite.Connection:
        """
        Returns a connected aiosqlite.Connection with WAL and foreign keys configured.
        Caller is responsible for closing or using `async with db.connection():`.
        """
        if not self._initialized:
            await self.init_db()

        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Provides an asynchronous context manager for database connection."""
        conn = await self.get_connection()
        try:
            yield conn
        finally:
            await conn.close()

    async def execute_query(self, query: str, parameters: tuple = ()) -> list:
        """Helper to run a read query returning list of row dictionaries."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON;")
            cursor = await db.execute(query, parameters)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
