import json

from ollama import chat

tools = []

toolMap = {}


def agent_loop(messages: list):
    while True:
        response = chat(model="qwen3:8b", messages=messages, tools=tools, think=True)
        # 把当前会话结果添加到messages中
        messages.append(response.message)
        # 如果大模型不需要调用工具，则直接返回
        if not response.message.tool_calls:
            return
        for tool_call in response.message.tool_calls:
            # 从toolMap中获取工具，并执行调用
            res = toolMap.get(tool_call.function.name)(**tool_call.function.arguments)
            # 把每一次调用结果都append到messages中
            messages.append({"role": "tool", "tool_name": tool_call.function.name, "content": json.dumps(res, ensure_ascii=False)})
