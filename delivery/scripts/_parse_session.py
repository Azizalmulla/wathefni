import json, re, sys

path = sys.argv[1] if len(sys.argv) > 1 else "/root/.openclaw-delivery/agents/riders/sessions/b26503bd-b205-478c-af52-69be644d0406.jsonl"

with open(path) as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    obj = json.loads(line.strip())
    msg = obj.get("message", {})
    role = msg.get("role", "")
    content = msg.get("content", "")

    if role == "user" and isinstance(content, str):
        cleaned = re.sub(r"```[^`]*```", "", content, flags=re.DOTALL)
        cleaned = re.sub(r"Conversation info.*?\n", "", cleaned)
        cleaned = re.sub(r"Sender.*?\n", "", cleaned)
        cleaned = re.sub(r"Untrusted context.*", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\[SYSTEM.*?\]", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\[/SYSTEM.*?\]", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"saved_.*\n", "", cleaned)
        cleaned = re.sub(r"last_.*\n", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            print(f"[{i}] USER: {cleaned[:300]}")

    elif role == "assistant":
        if isinstance(content, str) and content.strip():
            print(f"[{i}] BOT: {content[:300]}")
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        print(f"[{i}] BOT: {c['text'][:300]}")
                    elif c.get("type") == "tool_use":
                        print(f"[{i}] BOT_CALL: {c['name']}({json.dumps(c.get('input',{}))[:200]})")
