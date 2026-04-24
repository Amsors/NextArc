"""SecondClass 展示字段读取与文本格式化辅助。"""

from pyustc.young import SecondClass


def get_display_time(sc: SecondClass, field: str) -> str:
    day_of_week_chinese = {
        0: "周一",
        1: "周二",
        2: "周三",
        3: "周四",
        4: "周五",
        5: "周六",
        6: "周日",
    }

    if field == "create_time":
        ct = sc.create_time
        if ct is None:
            return "没有获取到数据！"
        return f"{ct.day}({day_of_week_chinese.get(ct.weekday(), '未知')}) {ct.strftime('%H:%M')}"

    if field == "apply_time":
        at = sc.apply_time
        if at is None:
            return "没有获取到数据！"
        if at.start.day == at.end.day:
            return (f"{at.start.strftime('%m-%d')}"
                    f" ({day_of_week_chinese.get(at.start.weekday(), '未知')}) "
                    f" {at.start.strftime('%H:%M')}"
                    f" ~ {at.end.strftime('%H:%M')}"
                    )
        return (f"{at.start.strftime('%m-%d')}"
                f" ({day_of_week_chinese.get(at.start.weekday(), '未知')}) "
                f"{at.start.strftime('%H:%M')} ~ "
                f"{at.end.strftime('%m-%d')} "
                f" ({day_of_week_chinese.get(at.end.weekday(), '未知')}) "
                f"{at.end.strftime('%H:%M')}"
                )

    if field == "hold_time":
        ht = sc.hold_time
        if ht is None:
            return "没有获取到数据！"
        if ht.start.day == ht.end.day:
            return (f"{ht.start.strftime('%m-%d')}"
                    f" ({day_of_week_chinese.get(ht.start.weekday(), '未知')}) "
                    f" {ht.start.strftime('%H:%M')}"
                    f" ~ {ht.end.strftime('%H:%M')}"
                    )
        return (f"{ht.start.strftime('%m-%d')}"
                f" ({day_of_week_chinese.get(ht.start.weekday(), '未知')}) "
                f"{ht.start.strftime('%H:%M')} ~ "
                f"{ht.end.strftime('%m-%d')}"
                f" ({day_of_week_chinese.get(ht.end.weekday(), '未知')}) "
                f"{ht.end.strftime('%H:%M')}"
                )

    return "出现错误！"


def get_status_text(sc: SecondClass) -> str:
    try:
        return sc.status.text
    except (AttributeError, ValueError):
        return f"未知状态({sc.data.get('itemStatus', 'unknown')})"


def get_apply_progress(sc: SecondClass) -> str:
    if sc.apply_num is None:
        return "未知"
    limit = sc.apply_limit if sc.apply_limit else "∞"
    return f"{sc.apply_num}/{limit}"


def get_module_name(sc: SecondClass) -> str:
    module = sc.module
    if module is None:
        return "未知"
    return module.text


def get_department_name(sc: SecondClass) -> str:
    dept = sc.department
    if dept is None:
        return "未知"
    return dept.name


def get_labels_text(sc: SecondClass) -> str:
    labels = sc.labels
    if not labels:
        return "无"
    return ", ".join(label.name for label in labels)


def get_conceive_text(sc: SecondClass) -> str:
    return sc.conceive or "未提供"


def get_description_text(sc: SecondClass) -> str:
    return sc.description or "未提供"


def get_place_info(sc: SecondClass) -> str:
    return sc.place_info or "未提供"


def get_participation_form(sc: SecondClass) -> str | None:
    if sc.participation_form:
        return sc.participation_form.text
    return None


def format_secondclass_for_list(sc: SecondClass, index: int, simple_format: bool = False) -> str:
    if simple_format:
        return f"[{index}] {sc.name}({'系列活动' if sc.is_series else '单次活动'})"

    ret: str = (
        f"[{index}] {sc.name}({'系列活动' if sc.is_series else '单次活动'})\n"
        f"    举办：{get_display_time(sc, 'hold_time')}\n"
        f"    报名：{get_display_time(sc, 'apply_time')}\n"
        f"    模块：{get_module_name(sc)}\n"
        f"    组织单位：{get_department_name(sc)}\n"
        f"    状态：{get_status_text(sc)}\n"
    )

    ret += f"    地点：{get_place_info(sc)}\n"

    if not sc.is_series:
        ret += f"    学时：{sc.valid_hour or '未知'}\n"
        ret += f"    报名：{get_apply_progress(sc)}\n"

    if sc.participation_form:
        ret += f"    参与形式：{get_participation_form(sc)}\n"

    return ret


def secondclass_to_display_dict(sc: SecondClass) -> dict[str, str]:
    return {
        "id": sc.id,
        "name": sc.name,
        "status": get_status_text(sc),
        "hold_time": get_display_time(sc, "hold_time"),
        "apply_time": get_display_time(sc, "apply_time"),
        "valid_hour": str(sc.valid_hour) if sc.valid_hour else "未知",
        "apply_progress": get_apply_progress(sc),
        "module": get_module_name(sc),
        "department": get_department_name(sc),
        "labels": get_labels_text(sc),
    }
