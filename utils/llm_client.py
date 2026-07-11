"""
通义千问 (Qwen) API 封装 — OpenAI 兼容模式

Endpoint: https://dashscope.aliyuncs.com/compatible-mode/v1
模型: qwen-plus（推荐，高性价比）/ qwen-turbo（更快）/ qwen-max（最强）

环境变量: DASHSCOPE_API_KEY（阿里云百炼 API Key）
申请地址: https://dashscope.console.aliyun.com/
"""
import json
import os
from datetime import date, datetime
from typing import Optional
import httpx


def _today_str() -> str:
    """今天日期 + 星期，供 LLM prompt 使用"""
    t = date.today()
    w = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][t.weekday()]
    return f"{t.strftime('%Y-%m-%d')} {w}"


class LLMClient:
    """通义千问 LLM 客户端"""

    # Qwen 推荐模型
    MODEL_FAST = "qwen-turbo"   # 极速，适合意图识别
    MODEL_BEST = "qwen-plus"    # 均衡，适合对话回复
    MODEL_MAX = "qwen-max"      # 最强，复杂推理

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = MODEL_BEST,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model
        self.base_url = base_url or self.BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # =========================================================================
    # 公开接口
    # =========================================================================

    def classify_intent(self, user_message: str, history: list[dict]) -> dict:
        """意图识别 + 槽位提取，返回结构化 JSON"""
        system = (
            "你是一个教育服务系统的意图识别引擎。根据用户消息识别意图并提取信息。\n\n"
            "返回 JSON（只返回 JSON，不要其他内容）：\n"
            "{\n"
            '  "intent": "leave_request|complaint_submit|application_progress|'
            'deadline_query|notification_query|score_query|upselling|psych_express|chat",\n'
            '  "slots": {\n'
            '    "leave_type": "sick|personal|emergency 或空",\n'
            '    "start_time": "YYYY-MM-DD HH:mm 或空",\n'
            '    "end_time": "YYYY-MM-DD HH:mm 或空",\n'
            '    "reason": "事由 或空",\n'
            '    "ticket_type": "complaint|suggestion|consult 或空",\n'
            '    "category": "签证办理|院校申请|生活服务|教学质量|其他 或空",\n'
            '    "complaint_content": "投诉内容 或空",\n'
            '    "deadline_days": "未来N天（默认30）"\n'
            "  },\n"
            '  "confidence": 0.0-1.0\n'
            "}\n\n"
            "意图含义：\n"
            "- leave_request: 请假（感冒/病假/事假/休息/不舒服）\n"
            "- complaint_submit: 投诉/建议/反馈/不满\n"
            "- application_progress: 查留学申请进度/offer\n"
            "- deadline_query: 查DDL/截止日期/考试\n"
            "- notification_query: 看通知/消息\n"
            "- score_query: 查成绩/分数/绩点/GPA/考试多少分\n"
            "- upselling: 想读博/读硕/考研/提升学历/继续深造\n"
            "- psych_express: 表达情绪/压力/焦虑/开心\n"
            "- chat: 打招呼/闲聊/感谢/其他\n\n"
            "注意：\n"
            "1. 从消息中提取时间时，把相对时间转为绝对日期。"
            f"今天是：{_today_str()}，解析规则：\n"
            "   - '明天' → 今天的日期+1天，时间默认 08:00\n"
            "   - '后天' → 今天+2天\n"
            "   - '下周X' → 下周对应的星期X\n"
            "   - 'N天后' → 今天+N天\n"
            "   - '上午' → 09:00, '下午' → 14:00, '晚上' → 19:00\n"
            "2. leave_type 无明确说明默认为 sick\n"
            "3. 无法确定的字段留空"
        )
        return self._call_json(system, user_message, history)

    def ask_follow_up(self, missing_field: str, intent_name: str, history: list[dict]) -> str:
        """生成追问，引导用户补充缺失信息"""
        prompts = {
            "leave_type": "请询问用户是病假、事假还是紧急情况。20字以内，友好。",
            "start_time": "请询问用户请假从什么时候开始。15字以内，友好。",
            "end_time": "请询问用户请假到什么时候结束。15字以内，友好。",
            "reason": "请询问用户请假原因。15字以内，友好。",
            "ticket_type": "请询问用户是投诉、建议还是咨询。20字以内，友好。",
            "category": "请询问反馈关于哪方面：签证/院校/生活/教学/其他。20字以内，友好。",
            "complaint_content": "请引导用户详细描述遇到的问题。25字以内，友好。",
        }
        prompt = prompts.get(missing_field, f"请引导用户补充 {missing_field}。15字以内。")
        return self._call_text(prompt, f"用户在提交{intent_name}时缺少{missing_field}", history)

    def generate_result_reply(
        self, intent_name: str, result: dict, history: list[dict]
    ) -> str:
        """根据业务执行结果生成自然语言回复"""
        success = result.get("success", True)
        if success:
            system = (
                f"用户成功完成了「{intent_name}」操作。请根据结果生成确认回复。\n"
                f"规则：50字以内，友好亲切，适当用 emoji。\n"
                f"操作结果：{json.dumps(result, ensure_ascii=False)}"
            )
        else:
            system = (
                f"用户的「{intent_name}」操作失败了。请根据错误生成安抚回复。\n"
                f"规则：30字以内，友好，建议稍后重试。\n"
                f"错误：{json.dumps(result, ensure_ascii=False)}"
            )
        return self._call_text(system, "", history)

    def generate_chat_reply(self, user_message: str, history: list[dict]) -> str:
        """闲聊回复"""
        system = (
            "你是一个温暖、友好的学生助手学姐。\n"
            "规则：40字以内，活泼亲切，可加 emoji。\n"
            "你可以帮学生：请假、投诉反馈、查申请进度、查DDL、看通知。\n"
            "不要编造课程、价格、政策等业务信息。"
        )
        return self._call_text(system, user_message, history)

    # =========================================================================
    # 内部方法
    # =========================================================================

    def _call_json(self, system: str, user: str, history: list[dict]) -> dict:
        """调 LLM 返回结构化 JSON"""
        raw = self._call_api(system, user, history, temperature=0.1)
        try:
            text = raw.strip()
            # 去掉 markdown 代码块
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()
            return json.loads(text)
        except json.JSONDecodeError:
            return {"intent": "chat", "slots": {}, "confidence": 0.0}

    def _call_text(self, system: str, user: str, history: list[dict]) -> str:
        """调 LLM 返回纯文本"""
        return self._call_api(system, user, history, temperature=0.7)

    def _call_api(
        self, system: str, user: str, history: list[dict], temperature: float
    ) -> str:
        """底层 API 调用"""
        messages = [{"role": "system", "content": system}]
        # 只保留最近 5 轮
        messages.extend(history[-10:])
        if user:
            messages.append({"role": "user", "content": user})

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 500,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return ""
