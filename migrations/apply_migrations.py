"""
Minimal migration runner for Real-Time Analytics Platform

Designed to run from the devcontainer with no additional dependencies
beyond what's already in services/ingestion
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add parent directory to Python path so we can import from services
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg not installed. Run: uv pip install asyncpg")
    sys.exit(1)


class Migration:
    """Represents a single SQL migration file."""

    def __init__(self, version: str, filepath: Path):
        self.version = version
        self.filepath = filepath
        self.name = filepath.stem

    def __repr__(self):
        return f"Migration(version={self.version}, name={self.name})"

    def __lt__(self, other):
        """Enable sorting by version (V1 < V2 < V3)."""
        # Extract numeric part: "V1" -> 1, "V10" -> 10
        self_num = int(self.version[1:])
        other_num = int(other.version[1:])
        return self_num < other_num


class MigrationRunner:
    """Lightweight migration orchestrator."""

    def __init__(self, database_url: str, migration_dir: Path):
        self.database_url = database_url
        self.migration_dir = migration_dir
        self.conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        """Establish database connection."""
        print(f"[INFO] Connecting to database...")

        # Parse asyncpg URL (remove +asyncpg if present)
        db_url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")

        try:
            self.conn = await asyncpg.connect(
                dsn=db_url,
                timeout=30,
                command_timeout=300,  # 5 min for long migrations
            )
            print(f"[INFO] Connected successfully")
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            raise

    async def close(self) -> None:
        """Close database connection."""
        if self.conn:
            await self.conn.close()
            print(f"[INFO] Connection closed")

    async def ensure_migrations_table(self) -> None:
        """Create schema_migrations tracking table."""
        print(f"[INFO] Ensuring schema_migrations table exists...")

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                execution_time_ms INTEGER,
                success BOOLEAN NOT NULL DEFAULT TRUE,
                error_message TEXT
            )
        """)

    async def acquire_lock(self) -> bool:
        """
        Acquire advisory lock to prevent concurrent migrations
        Returns True if lock acquired, False otherwise
        """
        print(f"[INFO] Acquiring migration lock...")

        # Lock ID: hash of "analytics_migrations" for uniqueness
        lock_id = 1234567890  # Derived from hash, but static for consistency

        acquired = await self.conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_id)

        if acquired:
            print(f"[INFO] Lock acquired (ID: {lock_id})")
        else:
            print(f"[ERROR] Another migration is in progress")
            print(f"[INFO] To force unlock: SELECT pg_advisory_unlock({lock_id});")

        return acquired

    async def release_lock(self) -> None:
        """Release advisory lock."""
        lock_id = 1234567890
        await self.conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
        print(f"[INFO] Lock released")

    async def validate_timescaledb(self) -> None:
        """Check if TimescaleDB is available (required for V3)."""
        print(f"[INFO] Validating TimescaleDB extension...")

        result = await self.conn.fetchrow(
            "SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb'"
        )

        if result:
            print(f"[INFO] TimescaleDB {result['extversion']} is installed")
        else:
            print(f"[WARN] TimescaleDB NOT found - V3 migration will fail")
            print(f"[WARN] Add to init.sql: CREATE EXTENSION timescaledb;")

    async def get_applied_migrations(self) -> List[str]:
        """Get list of successfully applied migrations."""
        rows = await self.conn.fetch(
            "SELECT version FROM schema_migrations WHERE success = TRUE ORDER BY version"
        )
        return [row["version"] for row in rows]

    def discover_migrations(self) -> List[Migration]:
        """Find all V*_*.sql files in migration directory."""
        print(f"[INFO] Scanning for migrations in {self.migration_dir}...")

        migration_files = sorted(self.migration_dir.glob("V*_*.sql"))
        migrations = []

        for filepath in migration_files:
            # Extract version: "V3_hypertables.sql" -> "V3"
            parts = filepath.stem.split("_")
            version = parts[0]
            migrations.append(Migration(version, filepath))

        migrations.sort()  # Sort by version number

        print(f"[INFO] Found {len(migrations)} migration(s):")
        for m in migrations:
            print(f"       - {m.version}: {m.name}")

        return migrations

    async def apply_migration(
        self, migration: Migration, dry_run: bool = False
    ) -> None:
        """Apply a single migration."""
        print(
            f"\n[INFO] {'[DRY RUN] ' if dry_run else ''}Applying {migration.version}: {migration.name}"
        )

        sql = migration.filepath.read_text()

        if dry_run:
            lines = sql.strip().split("\n")
            print(f"[INFO] Would execute {len(lines)} lines of SQL")
            print(f"[INFO] First few lines:")
            for line in lines[:5]:
                if line.strip() and not line.strip().startswith("--"):
                    print(f"       {line[:80]}...")
            return

        import time

        start = time.time()

        try:
            # Execute migration
            await self.conn.execute(sql)

            elapsed_ms = int((time.time() - start) * 1000)

            # Record success
            await self.conn.execute(
                """
                INSERT INTO schema_migrations (version, name, execution_time_ms, success)
                VALUES ($1, $2, $3, TRUE)
                ON CONFLICT (version) DO UPDATE
                SET applied_at = NOW(),
                    execution_time_ms = EXCLUDED.execution_time_ms,
                    success = TRUE,
                    error_message = NULL
            """,
                migration.version,
                migration.name,
                elapsed_ms,
            )

            print(f"[INFO] ✓ {migration.version} applied successfully ({elapsed_ms}ms)")

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)

            # Record failure
            await self.conn.execute(
                """
                INSERT INTO schema_migrations (version, name, execution_time_ms, success, error_message)
                VALUES ($1, $2, $3, FALSE, $4)
                ON CONFLICT (version) DO UPDATE
                SET applied_at = NOW(),
                    execution_time_ms = EXCLUDED.execution_time_ms,
                    success = FALSE,
                    error_message = EXCLUDED.error_message
            """,
                migration.version,
                migration.name,
                elapsed_ms,
                str(e),
            )

            print(f"[ERROR] ✗ {migration.version} failed: {e}")
            raise

    async def run(
        self, target_version: Optional[str] = None, dry_run: bool = False
    ) -> None:
        """Main migration execution."""
        try:
            # Setup
            await self.ensure_migrations_table()
            await self.validate_timescaledb()

            if not await self.acquire_lock():
                raise RuntimeError("Failed to acquire migration lock")

            # Determine what to run
            all_migrations = self.discover_migrations()
            applied = await self.get_applied_migrations()

            pending = [m for m in all_migrations if m.version not in applied]

            if target_version:
                pending = [m for m in pending if m.version <= target_version]

            if not pending:
                print(f"\n[INFO] No pending migrations - database is up to date")
                print(f"[INFO] Applied versions: {applied}")
                return

            print(
                f"\n[INFO] {'[DRY RUN] ' if dry_run else ''}Plan: Apply {len(pending)} migration(s)"
            )
            print(f"[INFO] Pending: {[m.version for m in pending]}")
            print(f"[INFO] Already applied: {applied}")

            if not dry_run:
                response = input(f"\n[PROMPT] Continue? [y/N]: ")
                if response.lower() != "y":
                    print(f"[INFO] Migration cancelled by user")
                    return

            # Apply migrations
            for migration in pending:
                await self.apply_migration(migration, dry_run=dry_run)

            print(f"\n[INFO] ✓ All migrations completed successfully")

        finally:
            await self.release_lock()


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Apply database migrations for Real-Time Analytics Platform"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument("--target-version", help="Apply up to this version (e.g., V2)")
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "DATABASE_URL", "postgresql://analytics:analytics@localhost:5432/analytics"
        ),
        help="Database connection URL",
    )

    args = parser.parse_args()

    # Migration directory is relative to this script
    migration_dir = Path(__file__).parent

    runner = MigrationRunner(args.database_url, migration_dir)

    try:
        await runner.connect()
        await runner.run(target_version=args.target_version, dry_run=args.dry_run)

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        sys.exit(1)

    finally:
        await runner.close()

    print(f"\n[INFO] Migration runner completed")


if __name__ == "__main__":
    asyncio.run(main())
