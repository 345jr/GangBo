import os
import json
import uuid
from pytz import timezone
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from astrbot.api.event import filter, AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.star.filter.event_message_type import EventMessageType
# from astrbot.core.star.filter.event_message_type import EventMessageType



@register("optis_plugin", "lopop", "广播任务插件", "1.0.0")
class TodoPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.users_file = os.path.join(plugin_dir,"users.json")
        self.users = self.load_users()
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
    

    def load_users(self):
        """从 JSON 文件中加载用户列表"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    else:
                        return []
            except Exception as e:
                logger.error(f"加载用户数据失败: {e}")
                return []
        else:
            return []

    def save_users(self):
        """将用户列表写入 JSON 文件"""
        try:
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(self.users, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")
    
    def add_user(self, user_origin: str):
        """如果用户未记录，则添加到列表中"""
        if user_origin not in self.users:
            self.users.append(user_origin)
            self.save_users()

    def compute_next_datetime(self, hour: int, minute: int):
        """计算距离现在最近的指定时间点"""
        now = datetime.now()
        run_date = now.replace(hour=hour,
                               minute=minute,
                               second=0,
                               microsecond=0)
        if run_date <= now:
            run_date += timedelta(days=1)
        return run_date         

    async def broadcast_message(self, content: str):
        """向所有记录的用户广播消息"""
        message_chain = MessageChain().message(content)
        for user in self.users:
            try:
                await self.context.send_message(user, message_chain)
            except Exception as e:
                logger.error(f"发送给用户 {user} 失败: {e}")

    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def record_user(self, event: AstrMessageEvent):
        self.add_user(event.unified_msg_origin)  
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("optip")
    async def optip(self, event: AstrMessageEvent, action: str, time_str: str = None, *, content: str = None):  
        action = action.lower().strip()
        if action == "list":
            if not self.users:
                yield event.plain_result("目前没有记录到任何用户。")
            else:
                msg = "已记录的用户列表：\n" + "\n".join(self.users)
                yield event.plain_result(msg)
        elif action == "immediate":
            if not content:
                yield event.plain_result("请提供广播内容。")
                return
            await self.broadcast_message(content)
            yield event.plain_result("立即广播已发送。")
        elif action == "schedule":
            if not time_str or not content:
                yield event.plain_result("请提供时间（格式 HH:MM）和广播内容。")
                return
            try:
                hour, minute = map(int, time_str.split(":"))
            except Exception as e:
                yield event.plain_result("时间格式错误，请使用 HH:MM 格式。")
                return
            run_date = self.compute_next_datetime(hour, minute)
            
            # 定时广播任务：使用 DateTrigger 实现一次性调度
            async def job_func():
                await self.broadcast_message(content)
                logger.info("定时广播任务已执行。")
            
            trigger = DateTrigger(run_date=run_date, timezone="Asia/Shanghai")
            self.scheduler.add_job(job_func, trigger=trigger, id=uuid.uuid4().hex)
            yield event.plain_result(f"广播任务已安排，在 {run_date.strftime('%Y-%m-%d %H:%M:%S')} 执行。")
        elif action == "help":
            msg="""管理广播任务：
          - action: "schedule" 定时广播, "immediate" 立即广播, "list" 查看已记录的用户列表
          - 若 action 为 "schedule"，需提供 time_str（格式 "HH:MM"）和广播内容
          - 若 action 为 "immediate"，直接广播提供的内容
          示例:
            /optip schedule 14:30 今天天气很好，记得出门防晒！
            /optip immediate 现在开始紧急广播！
            /optip list"""
            yield event.plain_result(msg)
        else:
            yield event.plain_result("未知的操作，请使用 'schedule', 'immediate' , 'list' , 'help'。")