"""/join 指令处理器"""

from pyustc.young import SecondClass

from src.models import UserSession
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.join")


class JoinHandler(CommandHandler):
    """报名活动指令"""
    
    @property
    def command(self) -> str:
        return "join"
    
    def get_usage(self) -> str:
        return "/join <序号> - 报名搜索结果的指定活动"
    
    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /join 指令"""
        if not self.check_dependencies():
            return "服务未初始化，请稍后重试"
        
        # 检查搜索上下文
        if not session.search or session.search.is_expired():
            return "❌ 请先使用 /search 搜索活动\n\n示例：/search 讲座"
        
        # 检查参数
        if not args:
            return f"用法：{self.get_usage()}\n\n当前搜索结果可用序号：1-{len(session.search.results)}"
        
        # 解析序号
        try:
            index = int(args[0])
            if index < 1:
                raise ValueError("序号必须大于0")
        except ValueError:
            return "❌ 无效的序号，请输入正整数\n\n示例：/join 1"
        
        # 获取搜索结果中的活动
        activity = session.search.get_result_by_index(index)
        
        if not activity:
            return f"❌ 序号超出范围，当前搜索结果共 {len(session.search.results)} 个活动"
        
        # 检查是否已报名
        if activity.applied:
            return f"⚠️ 您已经报名了「{activity.name}」"
        
        # 检查是否可报名
        if activity.status != 26:  # APPLYING = 26
            return f"❌ 「{activity.name}」当前状态不可报名\n状态：{activity.get_status_text()}"
        
        # 检查是否有待确认操作
        if session.confirm and not session.confirm.is_expired():
            return "⚠️ 您有一个待确认的操作，请先回复「确认」或「取消」"
        
        # 设置确认会话
        session.set_confirm("join", activity.id, activity.name)
        
        # 返回确认提示
        return session.confirm.get_confirm_prompt()
    
    async def execute_join(self, session: UserSession) -> str:
        """执行报名操作"""
        if not session.confirm or session.confirm.operation != "join":
            return "❌ 无效的操作"
        
        activity_id = session.confirm.activity_id
        activity_name = session.confirm.activity_name
        
        # 清除确认会话和搜索上下文
        session.clear_confirm()
        session.clear_search()
        
        logger.info(f"执行报名: {activity_name} ({activity_id})")
        
        try:
            # 使用认证会话执行报名
            from pyustc.young.second_class import SecondClass
            
            async with self._auth_manager.create_session_once():
                # 获取活动实例并报名
                # SecondClass 使用单例模式，需要提供 data 参数（可为 None）
                sc = SecondClass(activity_id, {})
                
                # 先更新活动信息（从服务器获取最新数据）
                await sc.update()
                
                # 检查是否可报名
                if not sc.applyable:
                    return f"❌ 「{activity_name}」当前不可报名\n状态：{sc.status.text if sc.status else '未知'}"
                
                # 检查是否需要报名信息
                if sc.need_sign_info:
                    # 如果需要报名信息，使用自动填充的 SignInfo
                    from pyustc.young.second_class import SignInfo
                    sign_info = await SignInfo.get_self()
                    result = await sc.apply(force=False, auto_cancel=False, sign_info=sign_info)
                else:
                    result = await sc.apply(force=False, auto_cancel=False)
                
                logger.info(f"apply() 返回值: {result}")
                
                if not result:
                    return f"❌ 报名失败：活动不可报名或名额已满"
            
            # 报名成功后，不立即扫描，避免覆盖结果
            # 让用户手动执行 /update 查看最新状态
            logger.info(f"报名成功: {activity_name}")
            return (
                f"✅ 已成功报名「{activity_name}」\n\n"
                f"💡 提示：执行 /update 可更新报名状态"
            )
            
        except Exception as e:
            logger.error(f"报名失败: {e}")
            return f"❌ 报名失败：{str(e)}"
