import subprocess
import json
from pathlib import Path
from ollama import chat
from dataclasses import dataclass, field

WORKDIR = Path.cwd()

PLAN_REMINDER_INTERVAL = 3


def bash(command: str) -> str:
    """
    Run a shell command.

    Args:
        command: Shell command to execute.
    """
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command"

    # 运行命令
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout(120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"


def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace:{p}")
    return path


def read_file(path: str, limit: int | None = None) -> str:
    """
    Read a text file.

    Args:
        path: Relative path of file.
        limit: Maximum lines to read.
    """
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"...({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    """
    Write content to a file.

    Args:
        path: Relative path of file.
        content: File content.
    """
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """
    Replace text in a file.

    Args:
        path: Relative path of file.
        old_text: Existing text.
        new_text: Replacement text.
    """
    try:
        file_path = safe_path(path)
        text = file_path.read_text()
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


@dataclass
class PlanItem:
    content: str
    status: str = "pending"


@dataclass
class PlanningState:
    items: list[PlanItem] = field(default_factory=list)
    rounds_since_update: int = 0


class TodoManager:
    def __init__(self):
        self.state = PlanningState()

    def update(self, items: list) -> str:
        if len(items) > 12:
            raise ValueError("Keep the session plan short (max 12 items)")
        normalized = []
        in_progress_count = 0
        for index, raw_item in enumerate(items):
            # 获取每一个计划项的内容、状态以及激活时描述
            content = str(raw_item.get("content", "")).strip()
            status = str(raw_item.get("status", "pending")).strip()

            # 校验字段内容
            if not content:
                raise ValueError(f"Item {index}: content required")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Item {index}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1
            normalized.append(PlanItem(content=content, status=status))
        # 同一时刻只能有一个计划项处于in_progress状态
        if in_progress_count > 1:
            raise ValueError("Only one plan item can be in_progress")
        self.state.items = normalized
        self.state.rounds_since_update = 0
        return self.render()

    def note_round_without_update(self) -> None:
        self.state.rounds_since_update += 1

    def reminder(self) -> str | None:
        """todo列表在指定轮数后依旧没有更新，需要提示llm

        Returns:
            str | None: _description_
        """
        if not self.state.items:
            return None
        if self.state.rounds_since_update < PLAN_REMINDER_INTERVAL:
            return None
        return "<reminder>Refresh your current plan before continuing.</reminder>"

    def render(self) -> str:
        """render plan item list in terminal

        Returns:
            str: _description_
        """
        if not self.state.items:
            return "No session plan yet."
        lines = []
        for item in self.state.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }[item.status]
            line = f"{marker} {item.content}"
            lines.append(line)

        completed = sum(1 for item in self.state.items if item.status == "completed")
        lines.append(f"\n({completed}/{len(self.state.items)} completed)")
        return "\n".join(lines)


TODO = TodoManager()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "执行shell命令",
            "parameter": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令名称"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容",
            "parameter": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径或文件名称",
                    },
                    "limit": {"type": "integer", "description": "限制读取最大行数"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把指定内容写到指定文件中",
            "parameter": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径或文件名称",
                    },
                    "content": {"type": "string", "description": "要写入的文件内容"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_file_content",
            "description": "使用新文本替换文件中的旧文本",
            "parameter": {
                "type": "object",
                "required": ["path", "old_text", "new_text"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径或文件名称",
                    },
                    "old_text": {"type": "string", "description": "旧文本"},
                    "new_text": {"type": "string", "description": "新文本"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "重写多阶段任务的当前执行计划",
            "parameter": {
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "多阶段任务的最新执行计划项列表",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "计划项的内容",
                            },
                            "status": {
                                "type": "string",
                                "description": "当前计划项的状态，只能是pending、in_progress、completed这三种状态中的一种",
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
        },
    },
]


TOOL_HANDLERS = {
    "bash": bash,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "todo": TODO.update,
}


def extrace_text(content) -> str:
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def agent_loop(messages: list):
    while True:
        # 跟模型对话并打印每次结果以及分割线
        response = chat(model="qwen3:8b", messages=messages, tools=TOOLS, think=True)
        print(response.model_dump_json())
        print("*" * 30)
        # 把当前会话结果添加到messages中
        messages.append(response.message)
        # 如果大模型不需要调用工具，则直接返回
        if not response.message.tool_calls:
            return

        # 记录是否需要调用todo相关的工具
        used_todo = False
        for tool_call in response.message.tool_calls:
            # 从toolMap中获取工具，并执行调用
            fn_name = tool_call.function.name
            if fn_name == "todo":
                used_todo = True
            fn_args = tool_call.function.arguments
            handler = TOOL_HANDLERS[fn_name]
            # 执行工具调用
            try:
                output = handler(**fn_args) if handler else f"Unknown tool: {fn_name}"
            except Exception as e:
                output = f"Error: {e}"
            # 打印工具调用结果
            print(f"> {fn_name}: {str(output)[:200]}")
            # 把调用结果append到messages中
            messages.append(
                {
                    "role": "tool",
                    "tool_name": fn_name,
                    "content": output,
                }
            )
        if used_todo:
            TODO.state.rounds_since_update = 0
        else:
            # 未更新todo轮次+1
            TODO.note_round_without_update()
            # 调用reminder判断是否要提醒大模型更新todo
            reminder = TODO.reminder()
            if reminder:
                messages.append(
                    {
                        "role": "system",
                        "content": reminder,
                    }
                )


SYSTEM = f"""你是{WORKDIR}目录下的一个编码agent.
如果你要完成多阶段任务，请使用todo工具.
在执行多阶段任务时务必确保同一时刻只有一个进行中的计划项.
每完成一个计划项则调用todo更新整个计划项列表.
"""

print(SYSTEM)


def extract_text(content) -> str:
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


if __name__ == "__main__":
    history = [{"role": "system", "conteng": SYSTEM}]
    while True:
        try:
            query = input("\033[36ms03 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()
