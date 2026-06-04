from pathlib import Path
import subprocess
import sys


def run_command(cmd: str):
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()
    }


print("=" * 60)
print("Python Environment Check")
print("=" * 60)

# Python
print(f"Python Version: {sys.version}")

# Python executable
print(f"Python Executable: {sys.executable}")

# 当前目录
print(f"Current Directory: {Path.cwd()}")

# 虚拟环境
print(f"Virtual Env: {sys.prefix}")

print()

print("=" * 60)
print("Shell Command Check")
print("=" * 60)

commands = [
    "pwd",
    "whoami",
    "git --version"
]

for cmd in commands:
    print(f"\n$ {cmd}")

    result = run_command(cmd)

    print(f"Return Code: {result['returncode']}")

    if result["stdout"]:
        print("STDOUT:")
        print(result["stdout"])

    if result["stderr"]:
        print("STDERR:")
        print(result["stderr"])