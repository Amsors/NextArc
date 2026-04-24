"""SecondClass 数据库操作"""

import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Self

from pyustc.young import SecondClass

from src.core.search_index import ensure_base_search_indexes, rebuild_full_text_search_index
from src.models.secondclass_mapper import secondclass_to_db_row
from src.utils.logger import get_logger

logger = get_logger("secondclass_db")


class DepartmentDB:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS departments (
                        id TEXT PRIMARY KEY,
                        departName TEXT NOT NULL,
                        isLeaf INTEGER NOT NULL,
                        createTime TEXT,
                        updateTime TEXT,
                        level TEXT NOT NULL,
                        pids TEXT NOT NULL
                    )
                """)
                conn.commit()

    def _create_backup(self) -> Path:
        backup_path = self.db_path.with_suffix(".db.bak")
        if self.db_path.exists():
            shutil.copy2(str(self.db_path), str(backup_path))
        return backup_path

    def _restore_backup(self, backup_path: Path):
        if not backup_path.exists():
            return

        try:
            if self.db_path.exists():
                self.db_path.unlink()
            shutil.move(str(backup_path), str(self.db_path))
        except OSError as e:
            raise RuntimeError(f"恢复数据库备份失败: {e}") from e

    def _remove_backup(self, backup_path: Path):
        if backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass

    def _validate_node(self, node: dict, parent_id: str | None = None) -> list[dict]:
        issues = []
        node_id = node.get("id", "unknown")
        node_title = node.get("title", "unknown")

        key = node.get("key")
        value = node.get("value")
        org_id = node.get("id")
        org_code = node.get("orgCode")

        if not (key == value == org_id == org_code):
            issues.append(
                f"[Validation] ID: {node_id}, Title: {node_title} - "
                f"key/value/id/orgCode mismatch: key={key}, value={value}, id={org_id}, orgCode={org_code}"
            )

        title = node.get("title")
        depart_name = node.get("departName")
        if title != depart_name:
            issues.append(
                f"[Validation] ID: {node_id}, Title: {node_title} - "
                f"title/departName mismatch: title={title}, departName={depart_name}"
            )

        level_str = node.get("level")
        pids_str = node.get("pids", "")

        if level_str is not None and pids_str is not None:
            try:
                level = int(level_str)
                pids_list = [pid for pid in pids_str.split(",") if pid]

                if level != len(pids_list):
                    issues.append(
                        f"[Validation] ID: {node_id}, Title: {node_title} - "
                        f"level/pids mismatch: level={level}, pids_count={len(pids_list)}, pids={pids_str}"
                    )

                if pids_list and pids_list[-1] != org_id:
                    issues.append(
                        f"[Validation] ID: {node_id}, Title: {node_title} - "
                        f"pids last element != id: pids_last={pids_list[-1] if pids_list else None}, id={org_id}"
                    )
            except ValueError:
                issues.append(
                    f"[Validation] ID: {node_id}, Title: {node_title} - "
                    f"Invalid level value: {level_str}"
                )

        return issues

    def _collect_nodes(self, node: dict) -> list[dict]:
        nodes = [node]

        if not node.get("isLeaf", True):
            children = node.get("children", [])
            for child in children:
                nodes.extend(self._collect_nodes(child))

        return nodes

    def import_from_json(self, data: list[dict]):
        if not data:
            raise ValueError("Input data is empty list")

        if len(data) != 1:
            raise ValueError(f"Expected exactly one root node, got {len(data)} nodes")

        root = data[0]
        root_id = root.get("id")
        root_title = root.get("title")

        if root_id != "211134":
            raise ValueError(f"Root node id must be '211134', got '{root_id}'")

        if root_title != "中国科学技术大学":
            raise ValueError(f"Root node title must be '中国科学技术大学', got '{root_title}'")

        backup_path = self._create_backup()

        try:
            all_nodes = self._collect_nodes(root)
            logger.info(f"Collected {len(all_nodes)} nodes from JSON")

            all_issues = []
            for node in all_nodes:
                issues = self._validate_node(node)
                all_issues.extend(issues)

            for issue in all_issues:
                logger.warning(issue)

            rows_to_insert = []
            for node in all_nodes:
                row = {
                    "id": str(node.get("id", "")),
                    "departName": str(node.get("departName", "")),
                    "isLeaf": 1 if node.get("isLeaf", False) else 0,
                    "createTime": node.get("createTime"),
                    "updateTime": node.get("updateTime"),
                    "level": str(node.get("level", "")),
                    "pids": str(node.get("pids", "")),
                }
                rows_to_insert.append(row)

            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM departments")
                    logger.info("Cleared existing data")

                    for row in rows_to_insert:
                        cursor.execute(
                            """
                            INSERT INTO departments (
                                id, departName, isLeaf, createTime, updateTime, level, pids
                            ) VALUES (
                                :id, :departName, :isLeaf, :createTime, :updateTime, :level, :pids
                            )
                            """,
                            row,
                        )

                    conn.commit()

            self._remove_backup(backup_path)

        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            self._restore_backup(backup_path)
            raise RuntimeError(f"Failed to import departments: {e}") from e

    def close(self):
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SecondClassDB:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS all_secondclass (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status INTEGER NOT NULL,
                        create_time TEXT,
                        apply_time TEXT,
                        hold_time TEXT,
                        tel TEXT NOT NULL,
                        valid_hour REAL,
                        apply_num INTEGER,
                        apply_limit INTEGER,
                        applied INTEGER,
                        need_sign_info INTEGER NOT NULL,
                        module TEXT,
                        department TEXT,
                        labels TEXT,
                        conceive TEXT NOT NULL,
                        is_series INTEGER NOT NULL,
                        place_info TEXT,
                        children_id TEXT,
                        parent_id TEXT,
                        scan_timestamp INTEGER NOT NULL,
                        deep_scaned BOOLEAN NOT NULL,
                        deep_scaned_time INTEGER,
                        participation_form INTEGER
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS enrolled_secondclass (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status INTEGER NOT NULL,
                        create_time TEXT,
                        apply_time TEXT,
                        hold_time TEXT,
                        tel TEXT NOT NULL,
                        valid_hour REAL,
                        apply_num INTEGER,
                        apply_limit INTEGER,
                        applied INTEGER,
                        need_sign_info INTEGER NOT NULL,
                        module TEXT,
                        department TEXT,
                        labels TEXT,
                        conceive TEXT NOT NULL,
                        is_series INTEGER NOT NULL,
                        place_info TEXT,
                        children_id TEXT,
                        parent_id TEXT,
                        scan_timestamp INTEGER NOT NULL,
                        deep_scaned BOOLEAN NOT NULL,
                        deep_scaned_time INTEGER,
                        participation_form INTEGER
                    )
                """)

                ensure_base_search_indexes(conn)
                conn.commit()

    def _secondclass_to_row(
            self,
            sc: SecondClass,
            children_ids: list[str] | None = None,
            parent_id: str | None = None,
            scan_timestamp: int | None = None,
            deep_scaned: bool = False,
            deep_scaned_time: int | None = None,
    ) -> dict[str, Any]:
        return secondclass_to_db_row(
            sc,
            children_ids=children_ids,
            parent_id=parent_id,
            scan_timestamp=scan_timestamp,
            deep_scaned=deep_scaned,
            deep_scaned_time=deep_scaned_time,
        )

    def _create_backup(self) -> Path | None:
        if not self.db_path.exists():
            return None

        backup_path = self.db_path.with_suffix(".db.bak")
        shutil.copy2(str(self.db_path), str(backup_path))
        return backup_path

    def _restore_backup(self, backup_path: Path | None):
        if backup_path is None or not backup_path.exists():
            return

        try:
            if self.db_path.exists():
                self.db_path.unlink()
            shutil.move(str(backup_path), str(self.db_path))
        except OSError as e:
            raise RuntimeError(f"恢复数据库备份失败: {e}") from e

    def _remove_backup(self, backup_path: Path | None):
        if backup_path is not None and backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass

    async def update_all_secondclass(
            self,
            secondclasses: list[SecondClass],
            deep_update: bool,
            expand_series: bool = False,
            max_concurrent: int = 5,
    ):
        scan_timestamp = int(time.time())
        rows_to_insert: list[dict[str, Any]] = []
        all_ids: set[str] = set()

        instances_to_update: list[SecondClass] = []
        parent_children_map: dict[str, list[SecondClass]] = {}

        for sc in secondclasses:
            all_ids.add(sc.id)

            if deep_update:
                instances_to_update.append(sc)

            if sc.is_series and expand_series:
                try:
                    children = await sc.get_children()
                    parent_children_map[sc.id] = children

                    for child in children:
                        if child.id not in all_ids:
                            all_ids.add(child.id)
                            if deep_update:
                                instances_to_update.append(child)
                except Exception as e:
                    parent_children_map[sc.id] = []

        if deep_update and instances_to_update:
            from .batch_updater import SecondClassBatchUpdater
            updater = SecondClassBatchUpdater(max_concurrent)

            _, failed = await updater.update_batch(instances_to_update, continue_on_error=True)
            if failed:
                logger.warning(f"Deep update: {len(failed)} instances failed to update")

        for sc in secondclasses:
            children = parent_children_map.get(sc.id, [])
            children_ids = [child.id for child in children] if children else None

            row = self._secondclass_to_row(
                sc,
                children_ids=children_ids,
                parent_id=None,
                scan_timestamp=scan_timestamp,
                deep_scaned=deep_update,
                deep_scaned_time=scan_timestamp if deep_update else None,
            )
            rows_to_insert.append(row)

            for child in children:
                child_row = self._secondclass_to_row(
                    child,
                    children_ids=None,
                    parent_id=sc.id,
                    scan_timestamp=scan_timestamp,
                    deep_scaned=deep_update,
                    deep_scaned_time=scan_timestamp if deep_update else None,
                )
                rows_to_insert.append(child_row)

        logger.info(f"Prepared {len(rows_to_insert)} rows to insert, {len(all_ids)} unique IDs")

        backup_path = self._create_backup()

        try:
            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    if all_ids:
                        placeholders = ",".join("?" * len(all_ids))
                        cursor.execute(
                            f"DELETE FROM all_secondclass WHERE id NOT IN ({placeholders})",
                            list(all_ids),
                        )
                        logger.info("Deleted records not in current batch")
                    else:
                        cursor.execute("DELETE FROM all_secondclass")
                        logger.info("Deleted all records (empty batch)")

                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO all_secondclass (
                            id, name, status, create_time, apply_time, hold_time,
                            tel, valid_hour, apply_num, apply_limit, applied,
                            need_sign_info, module, department, labels, conceive,
                            is_series, children_id, parent_id, scan_timestamp,
                            deep_scaned, deep_scaned_time,
                            place_info, participation_form
                        ) VALUES (
                            :id, :name, :status, :create_time, :apply_time, :hold_time,
                            :tel, :valid_hour, :apply_num, :apply_limit, :applied,
                            :need_sign_info, :module, :department, :labels, :conceive,
                            :is_series, :children_id, :parent_id, :scan_timestamp,
                            :deep_scaned, :deep_scaned_time,
                            :place_info, :participation_form
                        )
                        """,
                        rows_to_insert,
                    )

                    if rebuild_full_text_search_index(conn):
                        logger.debug("已同步 all_secondclass FTS 搜索索引")
                    else:
                        logger.debug("SQLite FTS5 trigram 不可用，跳过 FTS 搜索索引")

                    conn.commit()

            self._remove_backup(backup_path)
            logger.info("Backup removed, update completed successfully")

        except Exception as e:
            self._restore_backup(backup_path)
            raise RuntimeError(f"Failed to update all_secondclass: {e}") from e

    async def update_enrolled_secondclass(
            self,
            secondclasses: list[SecondClass],
            deep_update: bool,
            max_concurrent: int = 5,
    ):
        scan_timestamp = int(time.time())
        rows_to_insert: list[dict[str, Any]] = []
        all_ids: set[str] = set()

        for sc in secondclasses:
            all_ids.add(sc.id)

        if deep_update:
            from .batch_updater import SecondClassBatchUpdater
            updater = SecondClassBatchUpdater(max_concurrent)

            _, failed = await updater.update_batch(secondclasses, continue_on_error=True)
            if failed:
                logger.warning(f"Enrolled deep update: {len(failed)} instances failed to update")

        for sc in secondclasses:
            row = self._secondclass_to_row(
                sc,
                children_ids=None,
                parent_id=None,
                scan_timestamp=scan_timestamp,
                deep_scaned=False,
                deep_scaned_time=scan_timestamp if deep_update else None,
            )
            rows_to_insert.append(row)

        logger.info(f"Prepared {len(rows_to_insert)} rows to insert, {len(all_ids)} unique IDs")

        backup_path = self._create_backup()

        try:
            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    if all_ids:
                        placeholders = ",".join("?" * len(all_ids))
                        cursor.execute(
                            f"DELETE FROM enrolled_secondclass WHERE id NOT IN ({placeholders})",
                            list(all_ids),
                        )
                    else:
                        cursor.execute("DELETE FROM enrolled_secondclass")

                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO enrolled_secondclass (
                            id, name, status, create_time, apply_time, hold_time,
                            tel, valid_hour, apply_num, apply_limit, applied,
                            need_sign_info, module, department, labels, conceive,
                            is_series, children_id, parent_id, scan_timestamp,
                            deep_scaned, deep_scaned_time,
                            place_info, participation_form
                        ) VALUES (
                            :id, :name, :status, :create_time, :apply_time, :hold_time,
                            :tel, :valid_hour, :apply_num, :apply_limit, :applied,
                            :need_sign_info, :module, :department, :labels, :conceive,
                            :is_series, :children_id, :parent_id, :scan_timestamp,
                            :deep_scaned, :deep_scaned_time,
                            :place_info, :participation_form
                        )
                        """,
                        rows_to_insert,
                    )

                    conn.commit()
                    logger.info("Committed successfully")

            self._remove_backup(backup_path)

        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            self._restore_backup(backup_path)
            raise RuntimeError(f"Failed to update enrolled_secondclass: {e}") from e

    def get_scan_timestamp(self, table: str = "all_secondclass") -> int | None:
        if table not in ("all_secondclass", "enrolled_secondclass"):
            raise ValueError(f"Invalid table name: {table}")

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT MAX(scan_timestamp) FROM {table}")
                result = cursor.fetchone()
                return result[0] if result and result[0] is not None else None

    async def update_all_from_generator(
            self,
            sc_generator,
            deep_update: bool,
            expand_series: bool,
            max_concurrent: int = 5,
    ):
        secondclasses = []
        async for sc in sc_generator:
            secondclasses.append(sc)
        await self.update_all_secondclass(
            secondclasses,
            expand_series=expand_series,
            deep_update=deep_update,
            max_concurrent=max_concurrent,
        )

    async def update_enrolled_from_generator(
            self,
            sc_generator,
            deep_update: bool,
            max_concurrent: int = 5,
    ):
        secondclasses = []
        async for sc in sc_generator:
            secondclasses.append(sc)
        await self.update_enrolled_secondclass(
            secondclasses,
            deep_update=deep_update,
            max_concurrent=max_concurrent,
        )

    def close(self):
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
