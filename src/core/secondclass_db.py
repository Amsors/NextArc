"""Database operations for SecondClass data.

 migrated from pyustc library
"""

import json
import shutil
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from pyustc.young import SecondClass, Status
from pyustc.young.filter import Department, Label, Module, TimePeriod


class DepartmentDB:
    """Database manager for department/organization data from SecondClass platform."""

    def __init__(self, db_path: str | Path):
        """Initialize the department database manager.

        :param db_path: Path to the SQLite database file.
        :type db_path: str | Path
        """
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self):
        """Create departments table if it doesn't exist."""
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
        """Create a backup of the database file.

        :return: Path to the backup file.
        """
        backup_path = self.db_path.with_suffix(".db.bak")
        if self.db_path.exists():
            shutil.copy2(str(self.db_path), str(backup_path))
        return backup_path

    def _restore_backup(self, backup_path: Path):
        """Restore database from backup.

        :param backup_path: Path to the backup file.
        """
        if not backup_path.exists():
            return

        try:
            if self.db_path.exists():
                self.db_path.unlink()
            shutil.move(str(backup_path), str(self.db_path))
        except OSError as e:
            raise RuntimeError(f"Failed to restore database backup: {e}") from e

    def _remove_backup(self, backup_path: Path):
        """Remove the backup file.

        :param backup_path: Path to the backup file.
        """
        if backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass  # Ignore errors when removing backup

    def _validate_node(self, node: dict, parent_id: str | None = None) -> list[dict]:
        """Validate a node and return list of validation issues.

        :param node: The department node to validate.
        :param parent_id: The parent node ID for hierarchy validation.
        :return: List of validation issue messages.
        """
        issues = []
        node_id = node.get("id", "unknown")
        node_title = node.get("title", "unknown")

        # Check key, value, id, orgCode consistency
        key = node.get("key")
        value = node.get("value")
        org_id = node.get("id")
        org_code = node.get("orgCode")

        if not (key == value == org_id == org_code):
            issues.append(
                f"[Validation] ID: {node_id}, Title: {node_title} - "
                f"key/value/id/orgCode mismatch: key={key}, value={value}, id={org_id}, orgCode={org_code}"
            )

        # Check title and departName consistency
        title = node.get("title")
        depart_name = node.get("departName")
        if title != depart_name:
            issues.append(
                f"[Validation] ID: {node_id}, Title: {node_title} - "
                f"title/departName mismatch: title={title}, departName={depart_name}"
            )

        # Check level and pids consistency
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

                # Check if last element of pids equals own id
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
        """Recursively collect all nodes from the tree structure.

        :param node: The root node to start from.
        :return: List of all nodes (including the root).
        """
        nodes = [node]

        # If this node has children, recursively collect them
        if not node.get("isLeaf", True):
            children = node.get("children", [])
            for child in children:
                nodes.extend(self._collect_nodes(child))

        return nodes

    def import_from_json(self, data: list[dict]):
        """Import department data from JSON list.

        The JSON should be a list with exactly one element representing the root
        organization (id="211134", title="中国科学技术大学").

        :param data: List containing the root organization node.
        :type data: list[dict]
        :raises ValueError: If the input structure is invalid.
        :raises RuntimeError: If database operations fail.
        """
        # Validate input structure
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

        # Create backup before processing
        backup_path = self._create_backup()

        try:
            # Collect all nodes recursively
            all_nodes = self._collect_nodes(root)
            print(f"[DepartmentDB] Collected {len(all_nodes)} nodes from JSON", file=sys.stderr)

            # Validate all nodes and collect issues
            all_issues = []
            for node in all_nodes:
                issues = self._validate_node(node)
                all_issues.extend(issues)

            # Print all validation issues
            for issue in all_issues:
                print(issue, file=sys.stdout)

            # Prepare rows for database insertion
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

            # Insert into database
            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Clear existing data
                    cursor.execute("DELETE FROM departments")
                    print(f"[DepartmentDB] Cleared existing data", file=sys.stderr)

                    # Insert all nodes
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

            # Success: remove backup
            self._remove_backup(backup_path)

        except Exception as e:
            # Restore backup on failure
            print(f"[DepartmentDB] Exception occurred: {e}", file=sys.stderr)
            self._restore_backup(backup_path)
            raise RuntimeError(f"Failed to import departments: {e}") from e

    def close(self):
        """Close the database connection (no-op for sqlite3, but kept for API consistency)."""
        pass

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class SecondClassDB:
    """Database manager for SecondClass data."""

    def __init__(self, db_path: str | Path):
        """Initialize the database manager.

        :param db_path: Path to the SQLite database file.
        :type db_path: str | Path
        """
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Create all_secondclass table
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

                # Create enrolled_secondclass table with same structure
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

                conn.commit()

    @staticmethod
    def _timeperiod_to_json(tp: TimePeriod | None) -> dict[str, str] | None:
        """Convert TimePeriod to JSON-serializable dict."""
        if tp is None:
            return None
        return {
            "start": tp.start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": tp.end.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def _datetime_to_json(dt: datetime) -> dict[str, str]:
        """Convert datetime to JSON-serializable dict."""
        return {
            "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def _module_to_json(module: Module | None) -> dict[str, str] | None:
        """Convert Module to JSON-serializable dict."""
        if module is None:
            return None
        return {"value": module.value, "text": module.text}

    @staticmethod
    def _department_to_json(dept: Department | None) -> dict[str, Any] | None:
        """Convert Department to JSON-serializable dict."""
        if dept is None:
            return None
        return {"id": dept.id, "name": dept.name, "level": dept.level}

    @staticmethod
    def _labels_to_json(labels: list[Label] | None) -> list[dict[str, str]] | None:
        """Convert list of Label to JSON-serializable list."""
        if labels is None:
            return None
        return [{"id": label.id, "name": label.name} for label in labels]

    @staticmethod
    def _apply_num_to_json(apply_num: int | None) -> dict[str, Any]:
        """Convert apply_num (int | None) to JSON-serializable dict."""
        return {"value": apply_num, "is_none": apply_num is None}

    def _secondclass_to_row(
            self,
            sc: SecondClass,
            children_ids: list[str] | None = None,
            parent_id: str | None = None,
            scan_timestamp: int | None = None,
            deep_scaned: bool = False,
            deep_scaned_time: int | None = None,
    ) -> dict[str, Any]:
        """Convert SecondClass to a database row dict."""
        timestamp = scan_timestamp or int(time.time())

        # Handle complex types
        status_code = sc.status.code if sc.status else None

        return {
            "id": sc.id,
            "name": sc.name,
            "status": status_code,
            "create_time": json.dumps(self._datetime_to_json(sc.create_time)) if sc.create_time else None,
            "apply_time": json.dumps(self._timeperiod_to_json(sc.apply_time)) if sc.apply_time else None,
            "hold_time": json.dumps(self._timeperiod_to_json(sc.hold_time)) if sc.hold_time else None,
            "tel": sc.tel,
            "valid_hour": sc.valid_hour if sc.valid_hour is not None else None,
            "apply_num": sc.apply_num if sc.apply_num is not None else None,
            "apply_limit": sc.apply_limit if sc.apply_limit is not None else None,
            "applied": 1 if sc.applied else 0,
            "need_sign_info": 1 if sc.need_sign_info else 0,
            "module": json.dumps(self._module_to_json(sc.module)),
            "department": json.dumps(self._department_to_json(sc.department)),
            "labels": json.dumps(self._labels_to_json(sc.labels)),
            "conceive": sc.conceive,
            "is_series": 1 if sc.is_series else 0,
            "place_info": sc.place_info if sc.place_info is not None else None,
            "children_id": json.dumps(children_ids) if children_ids is not None else None,
            "parent_id": parent_id,
            "scan_timestamp": timestamp,
            "deep_scaned": deep_scaned,
            "deep_scaned_time": deep_scaned_time or None,
            "participation_form": sc.participation_form.code_str if sc.participation_form else None,
        }

    def _create_backup(self) -> Path | None:
        """Create a backup of the database file.

        :return: Path to the backup file, or None if no backup was created.
        """
        if not self.db_path.exists():
            return None

        backup_path = self.db_path.with_suffix(".db.bak")
        shutil.copy2(str(self.db_path), str(backup_path))
        return backup_path

    def _restore_backup(self, backup_path: Path | None):
        """Restore database from backup.

        :param backup_path: Path to the backup file.
        """
        if backup_path is None or not backup_path.exists():
            return

        try:
            if self.db_path.exists():
                self.db_path.unlink()
            shutil.move(str(backup_path), str(self.db_path))
        except OSError as e:
            raise RuntimeError(f"Failed to restore database backup: {e}") from e

    def _remove_backup(self, backup_path: Path | None):
        """Remove the backup file.

        :param backup_path: Path to the backup file.
        """
        if backup_path is not None and backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass  # Ignore errors when removing backup

    async def update_all_secondclass(
            self,
            secondclasses: list[SecondClass],
            deep_update: bool,
            expand_series: bool = False
    ):
        """Update the all_secondclass table with full refresh.

        This method performs a full update: it fetches series children if needed,
        builds parent-child relationships, and replaces all existing data.
        Records not present in the input will be deleted.

        :param secondclasses: List of SecondClass objects to store.
        :type secondclasses: list[SecondClass]
        :param expand_series: Whether to fetch and store children of series.
        :type expand_series: bool
        :raises RuntimeError: If the update fails and cannot be rolled back.
        """
        import sys

        scan_timestamp = int(time.time())
        rows_to_insert: list[dict[str, Any]] = []
        all_ids: set[str] = set()

        # Process each secondclass
        for sc in secondclasses:
            all_ids.add(sc.id)

            if deep_update:
                await sc.update()

            children_ids: list[str] | None = None
            parent_id: str | None = None

            if sc.is_series and expand_series:
                try:
                    children = await sc.get_children()
                    children_ids = [child.id for child in children]
                    # Add children to the processing list with parent_id set
                    for child in children:
                        if child.id not in all_ids:
                            all_ids.add(child.id)
                            if deep_update:
                                await child.update();
                            child_row = self._secondclass_to_row(
                                child,
                                children_ids=None,
                                parent_id=sc.id,
                                scan_timestamp=scan_timestamp,
                            )
                            rows_to_insert.append(child_row)
                except Exception as e:
                    # If fetching children fails, continue without children
                    children_ids = None

            row = self._secondclass_to_row(
                sc,
                children_ids=children_ids,
                parent_id=parent_id,
                scan_timestamp=scan_timestamp,
                deep_scaned=deep_update,
                deep_scaned_time=scan_timestamp if deep_update else None,
            )
            rows_to_insert.append(row)

        print(f"[DB Debug] Prepared {len(rows_to_insert)} rows to insert, {len(all_ids)} unique IDs", file=sys.stderr)

        # Create backup before updating
        backup_path = self._create_backup()

        try:
            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Delete records not in the current batch
                    if all_ids:
                        placeholders = ",".join("?" * len(all_ids))
                        cursor.execute(
                            f"DELETE FROM all_secondclass WHERE id NOT IN ({placeholders})",
                            list(all_ids),
                        )
                        print(f"[DB Debug] Deleted records not in current batch", file=sys.stderr)
                    else:
                        cursor.execute("DELETE FROM all_secondclass")
                        print(f"[DB Debug] Deleted all records (empty batch)", file=sys.stderr)

                    # Insert or replace all records
                    for row in rows_to_insert:
                        cursor.execute(
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
                            row,
                        )

                    conn.commit()

            # Success: remove backup
            self._remove_backup(backup_path)
            print(f"[DB Debug] Backup removed, update completed successfully", file=sys.stderr)

        except Exception as e:
            # Restore backup on failure
            self._restore_backup(backup_path)
            raise RuntimeError(f"Failed to update all_secondclass: {e}") from e

    async def update_enrolled_secondclass(
            self,
            secondclasses: list[SecondClass],
            deep_update: bool
    ):
        """Update the enrolled_secondclass table with full refresh.

        This method performs a full update: it replaces all existing data.
        Records not present in the input will be deleted.

        :param secondclasses: List of SecondClass objects to store.
        :type secondclasses: list[SecondClass]
        :raises RuntimeError: If the update fails and cannot be rolled back.
        """
        import sys

        scan_timestamp = int(time.time())
        rows_to_insert: list[dict[str, Any]] = []
        all_ids: set[str] = set()

        # Process each secondclass
        for sc in secondclasses:
            all_ids.add(sc.id)

            if deep_update:
                await sc.update()

            # For enrolled table, we don't track parent-child relationships
            row = self._secondclass_to_row(
                sc,
                children_ids=None,
                parent_id=None,
                scan_timestamp=scan_timestamp,
                deep_scaned=False,
                deep_scaned_time=scan_timestamp if deep_update else None,
            )
            rows_to_insert.append(row)

        print(f"[DB Debug] Prepared {len(rows_to_insert)} rows to insert, {len(all_ids)} unique IDs", file=sys.stderr)

        # Create backup before updating
        backup_path = self._create_backup()

        try:
            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Delete records not in the current batch
                    if all_ids:
                        placeholders = ",".join("?" * len(all_ids))
                        cursor.execute(
                            f"DELETE FROM enrolled_secondclass WHERE id NOT IN ({placeholders})",
                            list(all_ids),
                        )
                    else:
                        cursor.execute("DELETE FROM enrolled_secondclass")

                    # Insert or replace all records
                    for row in rows_to_insert:
                        cursor.execute(
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
                            row,
                        )

                    conn.commit()
                    print(f"[DB Debug] Committed successfully", file=sys.stderr)

            # Success: remove backup
            self._remove_backup(backup_path)

        except Exception as e:
            # Restore backup on failure
            print(f"[DB Debug] Exception occurred: {e}", file=sys.stderr)
            self._restore_backup(backup_path)
            raise RuntimeError(f"Failed to update enrolled_secondclass: {e}") from e

    def get_scan_timestamp(self, table: str = "all_secondclass") -> int | None:
        """Get the latest scan timestamp from a table.

        :param table: Table name to query ('all_secondclass' or 'enrolled_secondclass').
        :type table: str
        :return: The latest scan timestamp, or None if table is empty.
        """
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
    ):
        """Update the all_secondclass table from an async generator.

        This is a convenience method that collects items from an async generator
        (e.g., from SecondClass.find()) and updates the database.

        :param sc_generator: Async generator yielding SecondClass objects.
        :param expand_series: Whether to fetch and store children of series.
        :type expand_series: bool
        :raises RuntimeError: If the update fails and cannot be rolled back.

        Example:
            async with YouthService() as service:
                await service.login(cas_client)
                db = SecondClassDB("secondclass.db")
                await db.update_all_from_generator(
                    SecondClass.find(apply_ended=False),
                    expand_series=True
                )
        """
        secondclasses = []
        async for sc in sc_generator:
            secondclasses.append(sc)
        await self.update_all_secondclass(secondclasses, expand_series=expand_series, deep_update=deep_update)

    async def update_enrolled_from_generator(
            self,
            sc_generator,
            deep_update: bool,
    ):
        """Update the enrolled_secondclass table from an async generator.

        This is a convenience method that collects items from an async generator
        (e.g., from SecondClass.get_participated()) and updates the database.

        :param sc_generator: Async generator yielding SecondClass objects.
        :raises RuntimeError: If the update fails and cannot be rolled back.

        Example:
            async with YouthService() as service:
                await service.login(cas_client)
                db = SecondClassDB("secondclass.db")
                await db.update_enrolled_from_generator(
                    SecondClass.get_participated()
                )
        """
        secondclasses = []
        async for sc in sc_generator:
            secondclasses.append(sc)
        await self.update_enrolled_secondclass(secondclasses, deep_update=deep_update)

    def close(self):
        """Close the database connection (no-op for sqlite3, but kept for API consistency)."""
        pass

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
