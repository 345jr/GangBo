import asyncio
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.components import Plain

@register("todo_plugin", "lopop", "定时任务插件：创建待办事项并在指定时间提醒", "1.0.0")
class TodoPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 可以在这里初始化任务列表或其他状态
        self.tasks = []

    @filter.command("todo")
    async def todo_command(self, event: AstrMessageEvent, delay: int , content: str):
        """
        创建一个待办事项定时提醒。

        参数:
            delay (int): 延迟的秒数（等待多少秒后提醒）。
            content (str): 待办事项的内容。

        示例:
            /todo 10 吃饭
        """
        # 异步调度定时任务
        msg_origin = event.unified_msg_origin
        asyncio.create_task(self.run_schedule_todo(event.get_message_str(),delay,content,msg_origin))
        yield event.plain_result("定时任务已调度。")
        yield event.plain_result(f"{event.get_message_str()}")
    async def run_schedule_todo(self,event: AstrMessageEvent, delay: int, content: str, msg_origin: str):
        await self.schedule_todo(event, delay, content, msg_origin)
    async def schedule_todo(self,event: AstrMessageEvent, delay: int, content: str, msg_origin: str):
        # 等待指定的时间
        await asyncio.sleep(delay)
        yield event.plain_result("触发")
        # 调用 LLM API 来生成提醒文本
        func_tools_mgr = self.context.get_llm_tool_manager()
        llm_response = await self.context.get_using_provider().text_chat(
            prompt=f"请生成一段待办事项提醒文本，内容为：{content}",
            session_id=None,
            contexts=[],
            image_urls=[],
            func_tool=func_tools_mgr,
        )
        result_text = llm_response
        # 构造消息链，包含待办事项内容和 LLM 返回的提醒文本
        message_chain = [
            Plain(f"待办事项提醒:\n提醒内容: {result_text}")
        ]
        # 通过 unified_msg_origin 将消息发送回原会话
        await self.context.send_message(msg_origin, message_chain)