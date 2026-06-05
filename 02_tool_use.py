import subprocess
import json
from pathlib import Path
from ollama import chat

WORKDIR = Path.cwd()


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


def glob(pattern: str) -> str:
    """
    Find files matching a glob pattern.

    Args:
        pattern: Glob pattern, e.g. *.py
    """
    import glob as g

    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    bash,
    read_file,
    write_file,
    edit_file,
    glob,
]


TOOL_HANDLERS = {
    "bash": bash,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "glob": glob,
}


def agent_loop(messages: list):
    while True:
        response = chat(model="qwen3:8b", messages=messages, tools=TOOLS, think=True)
        print(response.model_dump_json())
        print("*" * 30)
        # 把当前会话结果添加到messages中
        messages.append(response.message)
        # 如果大模型不需要调用工具，则直接返回
        if not response.message.tool_calls:
            return
        for tool_call in response.message.tool_calls:
            # 从toolMap中获取工具，并执行调用
            fn_name = tool_call.function.name
            fn_args = tool_call.function.arguments
            result = TOOL_HANDLERS[fn_name](**fn_args)
            # 把每一次调用结果都append到messages中
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_call.function.name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )


if __name__ == "__main__":
    print("s02: Tool Use — 在 s01 基础上加了 4 个工具")
    print("输入问题，回车发送。输入 q 退出。\n")

    history = [
        {
            "role": "system",
            "content": """
You are a coding agent.

Use tools whenever helpful.

If user asks to read a file,
use read_file.

If file location is unknown,
use glob first.

Never claim you cannot access files
when a tool exists.
""",
        }
    ]
    while True:
        try:
            query = input("\033[36ms02 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        print(history)
