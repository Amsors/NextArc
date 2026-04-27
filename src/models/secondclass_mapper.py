"""SecondClass 与活动快照数据库行之间的转换。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Mapping

from pyustc.young import SecondClass
from pyustc.young.filter import Department, Label, Module, TimePeriod


def secondclass_from_db_row(row: Mapping[str, Any]) -> SecondClass:
    """从活动快照数据库行恢复 ``SecondClass`` 实例。"""

    data = {
        "id": row["id"],
        "itemName": row["name"],
        "itemStatus": row["status"],
        "tel": row["tel"],
        "booleanRegistration": row["applied"],
        "needSignInfo": "1" if row["need_sign_info"] else "0",
        "conceive": row["conceive"],
        "itemCategory": "1" if row["is_series"] else "0",
    }

    if row.get("create_time"):
        try:
            create_data = json.loads(row["create_time"])
            if create_data and "datetime" in create_data:
                dt = datetime.strptime(create_data["datetime"], "%Y-%m-%d %H:%M:%S")
                data["createTime"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    if row.get("apply_time"):
        try:
            apply_data = json.loads(row["apply_time"])
            if apply_data:
                if "start" in apply_data:
                    data["applySt"] = apply_data["start"]
                if "end" in apply_data:
                    data["applyEt"] = apply_data["end"]
        except (json.JSONDecodeError, KeyError):
            pass

    if row.get("hold_time"):
        try:
            hold_data = json.loads(row["hold_time"])
            if hold_data:
                if "start" in hold_data:
                    data["st"] = hold_data["start"]
                if "end" in hold_data:
                    data["et"] = hold_data["end"]
        except (json.JSONDecodeError, KeyError):
            pass

    if row.get("valid_hour") is not None:
        data["validHour"] = row["valid_hour"]

    if row.get("apply_num") is not None:
        data["applyNum"] = row["apply_num"]

    if row.get("apply_limit") is not None:
        data["peopleNum"] = row["apply_limit"]

    if row.get("module") and row["module"] != "null":
        try:
            module_data = json.loads(row["module"])
            if module_data:
                data["module"] = module_data.get("value")
                data["moduleName"] = module_data.get("text")
        except (json.JSONDecodeError, TypeError):
            pass

    if row.get("department") and row["department"] != "null":
        try:
            dept_data = json.loads(row["department"])
            if dept_data:
                data["businessDeptId"] = dept_data.get("id")
                data["bussinessDeptName"] = dept_data.get("name")
        except (json.JSONDecodeError, TypeError):
            pass

    if row.get("labels") and row["labels"] != "null":
        try:
            labels_data = json.loads(row["labels"])
            if labels_data and isinstance(labels_data, list):
                data["itemLable"] = ",".join(str(label.get("id", "")) for label in labels_data)
                data["lableNames"] = ",".join(str(label.get("name", "")) for label in labels_data)
        except (json.JSONDecodeError, TypeError):
            pass

    if row.get("children_id"):
        try:
            children_data = json.loads(row["children_id"])
            if children_data and isinstance(children_data, list):
                data["childrenIds"] = children_data
        except (json.JSONDecodeError, TypeError):
            pass

    if row.get("parent_id"):
        data["parentId"] = row["parent_id"]

    if row.get("place_info") is not None:
        data["placeInfo"] = row["place_info"]

    if row.get("participation_form") is not None:
        data["form"] = str(row["participation_form"])

    sc = SecondClass.from_dict(data)
    sc.data.clear()
    sc.data.update(data)
    return sc


def secondclass_to_db_row(
    sc: SecondClass,
    children_ids: list[str] | None = None,
    parent_id: str | None = None,
    scan_timestamp: int | None = None,
    deep_scaned: bool = False,
    deep_scaned_time: int | None = None,
) -> dict[str, Any]:
    """将 ``SecondClass`` 转为活动快照数据库行。"""

    timestamp = scan_timestamp or int(time.time())
    status_code = sc.status.code if sc.status else None
    resolved_children_ids = _resolve_children_ids(sc, children_ids)
    resolved_parent_id = parent_id if parent_id is not None else _resolve_parent_id(sc)

    return {
        "id": sc.id,
        "name": sc.name,
        "status": status_code,
        "create_time": json.dumps(_datetime_to_json(sc.create_time)) if sc.create_time else None,
        "apply_time": json.dumps(_timeperiod_to_json(sc.apply_time)) if sc.apply_time else None,
        "hold_time": json.dumps(_timeperiod_to_json(sc.hold_time)) if sc.hold_time else None,
        "tel": sc.tel,
        "valid_hour": sc.valid_hour if sc.valid_hour is not None else None,
        "apply_num": sc.apply_num if sc.apply_num is not None else None,
        "apply_limit": sc.apply_limit if sc.apply_limit is not None else None,
        "applied": 1 if sc.applied else 0,
        "need_sign_info": 1 if sc.need_sign_info else 0,
        "module": json.dumps(_module_to_json(sc.module)),
        "department": json.dumps(_department_to_json(sc.department)),
        "labels": json.dumps(_labels_to_json(sc.labels)),
        "conceive": sc.conceive,
        "is_series": 1 if sc.is_series else 0,
        "place_info": sc.place_info if sc.place_info is not None else None,
        "children_id": json.dumps(resolved_children_ids) if resolved_children_ids is not None else None,
        "parent_id": resolved_parent_id,
        "scan_timestamp": timestamp,
        "deep_scaned": deep_scaned,
        "deep_scaned_time": deep_scaned_time or None,
        "participation_form": sc.participation_form.code_str if sc.participation_form else None,
    }


def _timeperiod_to_json(tp: TimePeriod | None) -> dict[str, str] | None:
    if tp is None:
        return None
    return {
        "start": tp.start.strftime("%Y-%m-%d %H:%M:%S"),
        "end": tp.end.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _datetime_to_json(dt: datetime) -> dict[str, str]:
    return {
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _module_to_json(module: Module | None) -> dict[str, str] | None:
    if module is None:
        return None
    return {"value": module.value, "text": module.text}


def _department_to_json(dept: Department | None) -> dict[str, Any] | None:
    if dept is None:
        return None
    return {"id": dept.id, "name": dept.name, "level": dept.level}


def _labels_to_json(labels: list[Label] | None) -> list[dict[str, str]] | None:
    if labels is None:
        return None
    return [{"id": label.id, "name": label.name} for label in labels]


def _resolve_children_ids(sc: SecondClass, children_ids: list[str] | None) -> list[str] | None:
    if children_ids is not None:
        return children_ids

    raw_children_ids = sc.data.get("childrenIds")
    if isinstance(raw_children_ids, list):
        return [str(child_id) for child_id in raw_children_ids]
    return None


def _resolve_parent_id(sc: SecondClass) -> str | None:
    parent_id = sc.data.get("parentId")
    return str(parent_id) if parent_id is not None else None
