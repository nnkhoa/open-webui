import os
from urllib.parse import parse_qs, urlparse
from mysql.connector import pooling

_pools: dict[str, pooling.MySQLConnectionPool] = {}
_pool_metadata: dict[str, dict] = {}
_default_pool_key: str | None = None

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


def _build_pool(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in ["mysql", "mysql+pymysql"]:
        raise ValueError(
            "Invalid URL scheme. Must be mysql:// or mysql+pymysql://\n"
            f"Received: {parsed.scheme}://\n"
            "Examples:\n"
            "- mysql://USER:PASSWORD@HOST:PORT/DB\n"
            "- mysql://USER:PASSWORD@0.tcp.ngrok.io:PORT/DB"
        )

    host = parsed.hostname
    port = parsed.port
    user = parsed.username
    password = parsed.password or ""
    database = parsed.path.lstrip("/") if parsed.path else None
    qs = parse_qs(parsed.query or "", keep_blank_values=False)

    if not host:
        raise ValueError(f"Missing hostname in connection URL: {url}")
    if not database:
        raise ValueError(f"Missing database name in connection URL: {url}")
    if not user:
        raise ValueError(f"Missing username in connection URL: {url}")
    if not port:
        port = 3306

    pool_key = url.strip()
    pool_name = f"ai4bi_pool_{database.replace('-', '_').replace('.', '_')}_{abs(hash(pool_key)) % 100000}"

    env_pool_size = _parse_int(os.getenv("DB_POOL_SIZE", "32")) or 32
    url_pool_size = _parse_int(_qs_first(qs, "pool_size"))
    pool_size = url_pool_size if url_pool_size is not None else env_pool_size
    pool_size = max(1, min(int(pool_size), 64))

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

    pool = pooling.MySQLConnectionPool(
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

    metadata = {
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
    return pool_key, pool, metadata


def get_metadata(pool_key: str | None = None) -> dict:
    key = pool_key or _default_pool_key
    if not key:
        return {}
    return (_pool_metadata.get(key) or {}).copy()


def is_configured(pool_key: str | None = None) -> bool:
    if pool_key is None:
        return bool(_default_pool_key and _default_pool_key in _pools)
    return pool_key in _pools


def configure_pool(url: str, pool_key: str | None = None, make_default: bool = True):
    global _default_pool_key

    final_key = pool_key or url.strip()
    if final_key in _pools:
        if make_default:
            _default_pool_key = final_key
        return

    built_key, pool, metadata = _build_pool(url)
    final_key = pool_key or built_key
    _pools[final_key] = pool
    _pool_metadata[final_key] = metadata

    try:
        from .schema import reset_schema_cache
        reset_schema_cache()
    except Exception:
        pass

    if make_default or _default_pool_key is None:
        _default_pool_key = final_key


def disconnect_pool(pool_key: str | None = None):
    global _default_pool_key

    keys = [pool_key] if pool_key else list(_pools.keys())
    for key in keys:
        if key not in _pools:
            continue
        pool = _pools.pop(key)
        try:
            pool._remove_connections()
        except Exception:
            pass
        _pool_metadata.pop(key, None)
        if _default_pool_key == key:
            _default_pool_key = None

    try:
        from .schema import reset_schema_cache
        reset_schema_cache()
    except Exception:
        pass


def get_connection(pool_key: str | None = None):
    key = pool_key or _default_pool_key
    if not key or key not in _pools:
        raise Exception(
            "DATABASE_NOT_CONFIGURED: Please configure MCP connection first.\n"
            "Call POST /mcp/setup with a valid MySQL connection URL."
        )

    pool = _pools[key]
    metadata = _pool_metadata.get(key, {})

    try:
        conn = pool.get_connection()
    except Exception as e:
        raise Exception(
            f"Failed to get database connection: {str(e)}\n"
            f"Current config: host={metadata.get('host')}, "
            f"database={metadata.get('database')}, "
            f"user={metadata.get('user')}"
        )

    try:
        cursor = conn.cursor()
        cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
        cursor.execute("SET CHARACTER SET utf8mb4")
        cursor.close()
    except Exception:
        pass

    return conn
