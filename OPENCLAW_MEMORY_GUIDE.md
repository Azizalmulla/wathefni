# OpenClaw Memory Setup Guide — For Developer

## The Problem

OpenClaw agents are **stateless between sessions**. Every restart, the agent wakes up fresh. Memory only persists if it's written to files. Three ways memory gets lost:

1. **Session restart** — agent starts from scratch, only knows what it re-reads from files
2. **Context compaction** — when conversation hits ~200K tokens, older context gets summarized and details are lost
3. **Manual /reset or /new** — wipes working context without saving

## Memory Architecture (How It Works)

OpenClaw has 4 layers of memory:

| Layer | File/Location | Purpose |
|-------|--------------|---------|
| **Long-term memory** | `~/.openclaw/workspace/MEMORY.md` | Curated knowledge — agent reads every session. Decisions, preferences, key facts. |
| **Daily notes** | `~/.openclaw/workspace/memory/YYYY-MM-DD.md` | Raw daily logs. Agent reads today + yesterday on startup. |
| **Vector search index** | `~/.openclaw/memory/<agentId>.sqlite` | Semantic search over all memory files (BM25 + vector embeddings). |
| **Session transcripts** | Stored in sessions | Conversation history, gets compacted when too long. |

### Key Rule: "Text > Brain"
If the agent wants to remember something, it **must write it to a file**. "Mental notes" don't survive. Tell the agent: "If someone says remember this → write it to a file."

---

## Step 1: Create Memory Files

```bash
# Create MEMORY.md (long-term memory)
touch ~/.openclaw/workspace/MEMORY.md

# Create daily notes folder
mkdir -p ~/.openclaw/workspace/memory
```

Pre-populate `MEMORY.md` with key context about the business/client. The agent reads this every session start.

---

## Step 2: Enable Memory Flush (CRITICAL)

This saves context **before compaction destroys it**. When the conversation nears the context limit, OpenClaw triggers a silent prompt telling the agent to write important stuff to disk.

Add to `openclaw.json` under `agents.defaults`:

```json
{
  "agents": {
    "defaults": {
      "compaction": {
        "mode": "safeguard",
        "reserveTokensFloor": 20000,
        "memoryFlush": {
          "enabled": true,
          "softThresholdTokens": 4000,
          "systemPrompt": "Session nearing compaction. Store durable memories now.",
          "prompt": "Write any lasting notes to memory/YYYY-MM-DD.md; reply with NO_REPLY if nothing to store."
        }
      }
    }
  }
}
```

**How it works:** Flush triggers when session tokens reach `contextWindow - reserveTokensFloor - softThresholdTokens`. With 200K context, that's around 176K tokens. The agent gets a silent prompt to save memories, then compaction runs.

---

## Step 3: Enable Hybrid Memory Search

This lets the agent **semantically search** past memories — not just read files linearly, but find relevant stuff even when wording is different. Uses vector similarity + keyword matching (BM25).

Add to `openclaw.json` under `agents.defaults`:

```json
{
  "agents": {
    "defaults": {
      "memorySearch": {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "query": {
          "hybrid": {
            "enabled": true,
            "vectorWeight": 0.7,
            "textWeight": 0.3,
            "candidateMultiplier": 4
          }
        }
      }
    }
  }
}
```

**Provider options:**
- `openai` — fast, needs OpenAI API key (already configured)
- `gemini` — alternative, needs GEMINI_API_KEY
- `local` — no API costs, downloads ~600MB model, needs `pnpm approve-builds`

The agent gets two tools: `memory_search` (semantic search) and `memory_get` (read specific file).

---

## Step 4 (Optional): Install Mem0 Plugin

For **maximum persistence** — memory stored externally, survives compaction/resets/reinstalls.

```bash
openclaw plugins install @mem0/openclaw-mem0
```

Add to `openclaw.json`:

```json
{
  "plugins": {
    "mem0": {
      "apiKey": "your-mem0-api-key",
      "userId": "unique-user-id",
      "autoRecall": true,
      "autoCapture": true
    }
  }
}
```

Get API key from https://app.mem0.ai (free tier available).

**What it does:**
- **Auto-Recall:** Before every agent response, searches Mem0 for relevant memories and injects them into context
- **Auto-Capture:** After every response, extracts and stores new facts automatically
- No manual "write to MEMORY.md" needed — it's automatic
- Long-term (user-scoped, persists forever) vs. short-term (session-scoped) separation

**Note:** Mem0 is cloud-based (data on their servers). For privacy-sensitive clients (banks, government), use the built-in local memory instead, or self-host Mem0.

---

## Step 5 (Optional): QMD Backend (Fully Local)

For clients who need data sovereignty (no cloud):

```json
{
  "memory": {
    "backend": "qmd",
    "qmd": {
      "includeDefaultMemory": true,
      "update": {
        "interval": "5m",
        "debounceMs": 15000
      }
    }
  }
}


```bash
# Install QMD
bun install -g github.com/tobi/qmd
brew install sqlite
```

Fully local, no API keys. Combines BM25 + vectors + reranking. ~600MB disk for models.

---

## How the Agent's Session Start Should Work

Every time the agent wakes up, it should (in order):

1. Read `SOUL.md` — who it is
2. Read `USER.md` — who it's helping
3. Read `memory/YYYY-MM-DD.md` (today + yesterday) — recent context
4. Read `MEMORY.md` — long-term curated memory (only in private/main sessions, NOT in group chats for security)

This is already defined in `AGENTS.md`.

---

## Memory Maintenance (via Heartbeats)

The agent should periodically (every few days):

1. Read through recent `memory/YYYY-MM-DD.md` files
2. Identify significant events, lessons, insights
3. Update `MEMORY.md` with distilled learnings
4. Remove outdated info from `MEMORY.md`

Think of it like a human reviewing their journal. Daily files = raw notes. MEMORY.md = curated wisdom.

Configure heartbeat in `HEARTBEAT.md` to remind the agent to do memory maintenance.

---

## Quick Reference: Full Config Block

```json
{
  "agents": {
    "defaults": {
      "compaction": {
        "mode": "safeguard",
        "reserveTokensFloor": 20000,
        "memoryFlush": {
          "enabled": true,
          "softThresholdTokens": 4000,
          "systemPrompt": "Session nearing compaction. Store durable memories now.",
          "prompt": "Write any lasting notes to memory/YYYY-MM-DD.md; reply with NO_REPLY if nothing to store."
        }
      },
      "memorySearch": {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "query": {
          "hybrid": {
            "enabled": true,
            "vectorWeight": 0.7,
            "textWeight": 0.3,
            "candidateMultiplier": 4
          }
        }
      }
    }
  }
}
```

---

## Priority

1. ✅ **Must do:** Memory files + memory flush + hybrid search (Steps 1-3)
2. 🔜 **Should do:** Mem0 plugin for automatic capture (Step 4)
3. ⬜ **For enterprise clients:** QMD local backend (Step 5)

---

## Common Issues

- **"Agent forgets after restart"** → Memory files don't exist or aren't being read. Check `MEMORY.md` and `memory/` folder exist.
- **"Agent loses context mid-conversation"** → Memory flush not enabled. Compaction is destroying context before saving.
- **"Memory search returns nothing"** → Check `memorySearch.provider` is set and API key resolves. Check `~/.openclaw/memory/main.sqlite` has size > 0.
- **"Agent writes to memory but can't find it later"** → Hybrid search disabled. Enable `query.hybrid.enabled: true`.
- **"/reset wiped everything"** → That's expected. Memory flush only runs before compaction, not manual resets. Tell agent to save before resetting.
