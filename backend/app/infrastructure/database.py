"""One bounded pool per process. Never retry a transaction or an uncertain COMMIT."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import URL, Connection, Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.diagnostics import database_error
from app.infrastructure.settings import Settings
from app.services.errors import unavailable


def create_database(settings: Settings) -> Engine:
    engine = create_engine(
        URL.create(
            "mysql+pymysql",
            username=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
        ),
        pool_size=5,
        max_overflow=0,
        pool_timeout=1,
        pool_pre_ping=True,
        pool_recycle=300,
        isolation_level="READ COMMITTED",
        echo=False,
        hide_parameters=True,
        connect_args={
            "charset": "utf8mb4",
            "autocommit": False,
            "connect_timeout": 3,
            "read_timeout": 5,
            "write_timeout": 5,
            "ssl_ca": settings.db_ca,
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        },
    )

    @event.listens_for(engine, "connect")
    def initialize(connection: Any, record: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION time_zone = '+00:00'")
            cursor.execute(
                "SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_DATE,"
                "NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
            )
            cursor.execute("SET SESSION innodb_lock_wait_timeout = 1")
        connection.commit()

    return engine


@contextmanager
def transaction(engine: Engine, *, readonly: bool = False) -> Iterator[Connection]:
    try:
        with engine.connect() as connection:
            try:
                if readonly:
                    connection.execution_options(isolation_level="REPEATABLE READ")
                    connection.exec_driver_sql("START TRANSACTION READ ONLY")
                else:
                    connection.begin()
                yield connection
                if readonly:
                    connection.rollback()
                else:
                    connection.commit()
            except SQLAlchemyError:
                # Includes deadlocks, timeouts and ambiguous COMMIT. No automatic replay.
                try:
                    connection.rollback()
                finally:
                    connection.invalidate()
                raise
            except BaseException:
                connection.rollback()
                raise
    except SQLAlchemyError as error:
        database_error(error)
        raise unavailable() from None
