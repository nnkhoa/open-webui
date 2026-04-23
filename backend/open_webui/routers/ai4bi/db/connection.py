import os
from urllib.parse import parse_qs, urlparse
from mysql.connector import pooling

_pool = None
_configured = False
_metadata = {}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _qs_first(qs: dict[str, list[str]], key: str) -> str | None:
    items = qs.get(key)
    if not items:
        return None
    v = str(items[0]).strip()
    return v if v else None


def get_metadata() -> dict:
    """
    Get current connection metadata.

    Returns:
        dict: Connection metadata including host, database, user, pool info
              Returns empty dict if not configured
    """
    global _metadata
    return _metadata.copy() if _metadata else {}


def is_configured() -> bool:
    """
    Check if database pool is configured and ready.

    Returns:
        bool: True if pool is configured, False otherwise
    """
    global _configured
    return _configured

def configure_pool(url: str):
    """
    Configure database connection pool from MCP URL.

    Args:
        url: MySQL connection URL (mysql://user:pass@host:port/database)
             All parameters should come from user-provided MCP link.

    Raises:
        ValueError: If URL scheme is invalid
        Exception: If connection fails
    """
    global _pool, _configured, _metadata
    parsed = urlparse(url)

    # Validate URL scheme
    if parsed.scheme not in ["mysql", "mysql+pymysql"]:
        raise ValueError(
            "Invalid URL scheme. Must be mysql:// or mysql+pymysql://\n"
            f"Received: {parsed.scheme}://\n"
            "Examples:\n"
            "- mysql://USER:PASSWORD@HOST:PORT/DB\n"
            "- mysql://USER:PASSWORD@0.tcp.ngrok.io:PORT/DB"
        )

    # Extract connection parameters from URL (no hard-coded defaults)
    host = parsed.hostname
    port = parsed.port
    user = parsed.username
    password = parsed.password or ""
    database = parsed.path.lstrip("/") if parsed.path else None
    qs = parse_qs(parsed.query or "", keep_blank_values=False)

    # Validate required parameters
    if not host:
        raise ValueError(f"Missing hostname in connection URL: {url}")
    if not database:
        raise ValueError(f"Missing database name in connection URL: {url}")
    if not user:
        raise ValueError(f"Missing username in connection URL: {url}")
    if not port:
        # MySQL default is 3306; still allow missing port for convenience.
        port = 3306

    # Remove existing pool if present
    if _pool is not None:
        try:
            _pool._remove_connections()
        except Exception:
            pass
    # Reset schema cache so the app reflects the newly connected database
    try:
        from .schema import reset_schema_cache
        reset_schema_cache()
    except Exception:
        pass

    # Create dynamic pool name based on database
    pool_name = f"ai4bi_pool_{database.replace('-', '_').replace('.', '_')}"

    # Get pool size from environment or use default
    env_pool_size = _parse_int(os.getenv("DB_POOL_SIZE", "32")) or 32
    url_pool_size = _parse_int(_qs_first(qs, "pool_size"))
    pool_size = url_pool_size if url_pool_size is not None else env_pool_size
    pool_size = max(1, min(int(pool_size), 64))

    # Optional connection options from querystring (useful for ngrok / TLS)
    ssl_disabled = _parse_bool(_qs_first(qs, "ssl_disabled"))
    ssl_verify_cert = _parse_bool(_qs_first(qs, "ssl_verify_cert"))
    ssl_verify_identity = _parse_bool(_qs_first(qs, "ssl_verify_identity"))
    ssl_ca = _qs_first(qs, "ssl_ca")
    ssl_cert = _qs_first(qs, "ssl_cert")
    ssl_key = _qs_first(qs, "ssl_key")
    ssl_cipher = _qs_first(qs, "ssl_cipher")
    tls_versions_raw = _qs_first(qs, "tls_versions")
    tls_ciphersuites_raw = _qs_first(qs, "tls_ciphersuites")

    connection_timeout = _parse_int(_qs_first(qs, "connection_timeout"))
    read_timeout = _parse_int(_qs_first(qs, "read_timeout"))
    write_timeout = _parse_int(_qs_first(qs, "write_timeout"))

    charset = _qs_first(qs, "charset") or "utf8mb4"
    collation = _qs_first(qs, "collation") or "utf8mb4_unicode_ci"

    extra_kwargs: dict = {}
    if ssl_disabled is not None:
        extra_kwargs["ssl_disabled"] = ssl_disabled
    if ssl_verify_cert is not None:
        extra_kwargs["ssl_verify_cert"] = ssl_verify_cert
    if ssl_verify_identity is not None:
        extra_kwargs["ssl_verify_identity"] = ssl_verify_identity
    if ssl_ca:
        extra_kwargs["ssl_ca"] = ssl_ca
    if ssl_cert:
        extra_kwargs["ssl_cert"] = ssl_cert
    if ssl_key:
        extra_kwargs["ssl_key"] = ssl_key
    if ssl_cipher:
        extra_kwargs["ssl_cipher"] = ssl_cipher
    if tls_versions_raw:
        extra_kwargs["tls_versions"] = [v.strip() for v in tls_versions_raw.split(",") if v.strip()]
    if tls_ciphersuites_raw:
        extra_kwargs["tls_ciphersuites"] = [v.strip() for v in tls_ciphersuites_raw.split(",") if v.strip()]
    if connection_timeout is not None:
        extra_kwargs["connection_timeout"] = connection_timeout
    if read_timeout is not None:
        extra_kwargs["read_timeout"] = read_timeout
    if write_timeout is not None:
        extra_kwargs["write_timeout"] = write_timeout

    _pool = pooling.MySQLConnectionPool(
        pool_name=pool_name,
        pool_size=pool_size,
        pool_reset_session=True,
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset=charset,
        collation=collation,
        use_unicode=True,
        use_pure=True,
        **extra_kwargs,
    )

    _configured = True
    _metadata = {
        "url": url,
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "pool_name": pool_name,
        "pool_size": pool_size,
        "charset": charset,
        "collation": collation,
    }

def disconnect_pool():
    """
    Disconnect and remove the database connection pool.

    This clears all connections and resets the configuration.
    Safe to call even if pool is not configured.
    """
    global _pool, _configured, _metadata

    if _pool is not None:
        try:
            _pool._remove_connections()
        except Exception as e:
            print(f"Warning: Error removing connections: {e}")

    _pool = None
    _configured = False
    _metadata = {}
    # Reset schema cache when disconnecting
    try:
        from .schema import reset_schema_cache
        reset_schema_cache()
    except Exception:
        pass

def get_connection():
    """
    Get a connection from the pool.

    Returns:
        MySQL connection object

    Raises:
        Exception: If database pool is not configured
        Exception: If connection fails
    """
    global _pool

    if not _configured or _pool is None:
        raise Exception(
            "DATABASE_NOT_CONFIGURED: Please configure MCP connection first.\n"
            "Call POST /mcp/setup with a valid MySQL connection URL."
        )

    try:
        conn = _pool.get_connection()
    except Exception as e:
        raise Exception(
            f"Failed to get database connection: {str(e)}\n"
            f"Current config: host={_metadata.get('host')}, "
            f"database={_metadata.get('database')}, "
            f"user={_metadata.get('user')}"
        )

    # Set UTF-8 encoding for proper Unicode support
    try:
        cursor = conn.cursor()
        cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
        cursor.execute("SET CHARACTER SET utf8mb4")
        cursor.execute("SET character_set_connection=utf8mb4")
        cursor.execute("SET character_set_results=utf8mb4")
        cursor.execute("SET character_set_client=utf8mb4")
        cursor.close()
    except Exception as e:
        # Log but don't fail - encoding settings are not critical
        print(f"Warning: Failed to set connection encoding: {e}")

    return conn
