import os
import json
from pytz import timezone
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from astrbot.api.event import filter, AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.star.filter.event_message_type import EventMessageType



@register("optis_plugin", "lopop", "广播任务插件", "1.0.0")
class OpTipPlugin(Star):

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

    async def execute_task(self, content: str):
        """任务到时时调用：使用 LLM 生成提醒文本并发送给用户"""
        config = self.context.get_config()
        persona_config = config["persona"][0]
        prompt = persona_config["prompt"]

        llm_response = await self.context.get_using_provider().text_chat(
            prompt=content,
            session_id=None,
            contexts=[],
            image_urls=[],
            func_tool=None,
            system_prompt=prompt,
        )
        message_chain = MessageChain().message(llm_response.completion_text)
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
        if action == "用户列表":
            if not self.users:
                yield event.plain_result("目前没有记录到任何用户。")
            else:
                filter_users = [user for user in self.users if not user.startswith("webchat:FriendMessage:webchat!astrbot!")]   
                msg = "已记录的用户列表：\n" + "\n".join(filter_users)
                yield event.plain_result(msg)
        elif action == "立即":
            if not content:
                yield event.plain_result("请提供广播内容。")
                return
            await self.execute_task(content)
            yield event.plain_result("立即广播已发送。")
        elif action == "每日定时":
            if not time_str or not content:
                yield event.plain_result("请提供时间（格式 HH:MM)和广播内容。")
                return
            try:
                hour, minute = map(int, time_str.split(":"))
            except Exception as e:
                yield event.plain_result("时间格式错误，请使用 HH:MM 格式。")
                return
          
            # 定时广播任务：使用 CronTrigger 实现一次性调度
            async def job_func():
                await self.execute_task(content)
                logger.info("每日定时广播任务已执行。")
            job_name = content
            trigger = CronTrigger(hour=hour,minute=minute,timezone="Asia/Shanghai")
            self.scheduler.add_job(job_func, trigger=trigger, id=job_name)
            yield event.plain_result(f"广播任务已安排")

        elif action == "广播列表":
            if not self.scheduler.get_jobs():
                yield event.plain_result("目前没有记录到任何广播任务。")
            else :
                jobs = self.scheduler.get_jobs()
                msg = "已记录的广播任务列表：\n" + "\n".join([f"{job.id}" for job in jobs])
                yield event.plain_result(msg)
        elif action == "删除广播": 
            if not content:
                yield event.plain_result("请提供广播的名字。")
            else :
                try:
                    self.scheduler.remove_job(content)
                    yield event.plain_result(f"已删除广播任务 {content}")
                except Exception as e:
                    logger.error(f"移除调度任务失败: {e}")

        elif action == "帮助":
            msg = """
管理广播任务：
- 操作类型:
  - 定时广播
    - 示例: `/optip 每日定时 10:00 搜索一些励志的句子并告诉我`
  - 立即广播
    - 示例: `/optip 立即 None 我有一件事情要和大家说`
  - 查看已记录的用户列表
    - 示例: `/optip 用户列表`
  - 查看广播每日任务
    - 示例: `/optip 广播列表 `
  - 删除已经设置的广播每日任务
    - 示例: `/optip 删除广播 None <广播ID>`
"""
            yield event.plain_result(msg)
        else:
            yield event.plain_result("未知的操作")