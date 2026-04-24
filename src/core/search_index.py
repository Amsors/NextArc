"""活动快照搜索索引维护。"""

from __future__ import annotations

import sqlite3

import aiosqlite

BASE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_all_secondclass_status ON all_secondclass (status)",
    "CREATE INDEX IF NOT EXISTS idx_all_secondclass_name ON all_secondclass (name)",
    "CREATE INDEX IF NOT EXISTS idx_all_secondclass_scan_timestamp ON all_secondclass (scan_timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_all_secondclass_parent_id ON all_secondclass (parent_id)",
)

FTS_TABLE = "all_secondclass_fts"
FTS_COLUMNS = ["id", "name", "department", "labels", "conceive", "place_info"]
MIN_TRIGRAM_QUERY_LENGTH = 3


def keyword_can_use_trigram(keyword: str) -> bool:
    """判断关键词是否适合 trigram FTS 查询。"""

    return len(keyword.strip()) >= MIN_TRIGRAM_QUERY_LENGTH


def quote_fts_query(keyword: str) -> str:
    """将用户关键词转为 FTS5 phrase query，避免特殊字符破坏 MATCH 语法。"""

    escaped_keyword = keyword.strip().replace('"', '""')
    return f'"{escaped_keyword}"'


def ensure_base_search_indexes(conn: sqlite3.Connection) -> None:
    """为 all_secondclass 创建基础 B-tree 索引。"""

    for sql in BASE_INDEX_SQL:
        conn.execute(sql)


def supports_trigram_fts5(conn: sqlite3.Connection) -> bool:
    """检测当前 SQLite 连接是否支持 FTS5 trigram tokenizer。"""

    table_name = "nextarc_fts5_trigram_probe"
    try:
        conn.execute(f"DROP TABLE IF EXISTS temp.{table_name}")
        conn.execute(
            f"CREATE VIRTUAL TABLE temp.{table_name} "
            "USING fts5(content, tokenize='trigram')"
        )
        conn.execute(
            f"INSERT INTO temp.{table_name}(content) VALUES (?)",
            ("人工智能讲座",),
        )
        row = conn.execute(
            f"SELECT 1 FROM temp.{table_name} WHERE {table_name} MATCH ? LIMIT 1",
            ("人工智能",),
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        try:
            conn.execute(f"DROP TABLE IF EXISTS temp.{table_name}")
        except sqlite3.Error:
            pass


def ensure_full_text_search_index(conn: sqlite3.Connection) -> bool:
    """创建 trigram FTS 搜索表；不支持时返回 False。"""

    try:
        if not supports_trigram_fts5(conn):
            return False

        _drop_incompatible_fts_table(conn)
        conn.execute(_create_fts_sql())
        return True
    except sqlite3.Error:
        return False


def rebuild_full_text_search_index(conn: sqlite3.Connection) -> bool:
    """用 all_secondclass 当前内容重建 FTS 搜索表。"""

    conn.execute("SAVEPOINT nextarc_fts_rebuild")
    try:
        if not ensure_full_text_search_index(conn):
            conn.execute("ROLLBACK TO nextarc_fts_rebuild")
            return False

        conn.execute(f"DELETE FROM {FTS_TABLE}")
        conn.execute(_rebuild_fts_insert_sql())
        return True
    except sqlite3.Error:
        try:
            conn.execute("ROLLBACK TO nextarc_fts_rebuild")
        except sqlite3.Error:
            pass
        return False
    finally:
        try:
            conn.execute("RELEASE nextarc_fts_rebuild")
        except sqlite3.Error:
            pass


async def has_full_text_search_index(conn: aiosqlite.Connection) -> bool:
    """判断数据库中是否已存在 FTS 搜索表。"""

    async with conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (FTS_TABLE,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def supports_trigram_fts5_async(conn: aiosqlite.Connection) -> bool:
    """异步检测当前 SQLite 连接是否支持 FTS5 trigram tokenizer。"""

    table_name = "nextarc_fts5_trigram_probe"
    try:
        await conn.execute(f"DROP TABLE IF EXISTS temp.{table_name}")
        await conn.execute(
            f"CREATE VIRTUAL TABLE temp.{table_name} "
            "USING fts5(content, tokenize='trigram')"
        )
        await conn.execute(
            f"INSERT INTO temp.{table_name}(content) VALUES (?)",
            ("人工智能讲座",),
        )
        async with conn.execute(
            f"SELECT 1 FROM temp.{table_name} WHERE {table_name} MATCH ? LIMIT 1",
            ("人工智能",),
        ) as cursor:
            return await cursor.fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        try:
            await conn.execute(f"DROP TABLE IF EXISTS temp.{table_name}")
        except sqlite3.Error:
            pass


async def ensure_full_text_search_index_async(conn: aiosqlite.Connection) -> bool:
    """异步创建 trigram FTS 搜索表；不支持时返回 False。"""

    try:
        if not await supports_trigram_fts5_async(conn):
            return False

        await _drop_incompatible_fts_table_async(conn)
        await conn.execute(_create_fts_sql())
        return True
    except sqlite3.Error:
        return False


async def rebuild_full_text_search_index_async(conn: aiosqlite.Connection) -> bool:
    """异步重建 FTS 搜索表。"""

    await conn.execute("SAVEPOINT nextarc_fts_rebuild")
    try:
        if not await ensure_full_text_search_index_async(conn):
            await conn.execute("ROLLBACK TO nextarc_fts_rebuild")
            return False

        await conn.execute(f"DELETE FROM {FTS_TABLE}")
        await conn.execute(_rebuild_fts_insert_sql())
        return True
    except sqlite3.Error:
        try:
            await conn.execute("ROLLBACK TO nextarc_fts_rebuild")
        except sqlite3.Error:
            pass
        return False
    finally:
        try:
            await conn.execute("RELEASE nextarc_fts_rebuild")
        except sqlite3.Error:
            pass


def _create_fts_sql() -> str:
    columns_sql = ", ".join(
        ["id UNINDEXED", "name", "department", "labels", "conceive", "place_info"]
    )
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} "
        f"USING fts5({columns_sql}, tokenize='trigram')"
    )


def _rebuild_fts_insert_sql() -> str:
    return f"""
        INSERT INTO {FTS_TABLE} (id, name, department, labels, conceive, place_info)
        SELECT
            id,
            COALESCE(name, ''),
            COALESCE(department, ''),
            COALESCE(labels, ''),
            COALESCE(conceive, ''),
            COALESCE(place_info, '')
        FROM all_secondclass
    """


def _drop_incompatible_fts_table(conn: sqlite3.Connection) -> None:
    columns = _get_table_columns(conn, FTS_TABLE)
    if columns and columns != FTS_COLUMNS:
        conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")


async def _drop_incompatible_fts_table_async(conn: aiosqlite.Connection) -> None:
    columns = await _get_table_columns_async(conn, FTS_TABLE)
    if columns and columns != FTS_COLUMNS:
        await conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")


def _get_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]


async def _get_table_columns_async(conn: aiosqlite.Connection, table: str) -> list[str]:
    columns: list[str] = []
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        async for row in cursor:
            columns.append(str(row[1]))
    return columns
