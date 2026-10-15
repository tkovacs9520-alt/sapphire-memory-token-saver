# sapphire-memory-token-saver — DEPRECATED

> **This project has moved.**
> **→ [sapphire-session-continuity](https://github.com/tkovacs9520-alt/sapphire-session-continuity)**

This repository never shipped working plugin code, and the design behind it has
been replaced. Please use the successor linked above.

## What went wrong

The original idea was to cut token usage by compressing conversation memory.
Two problems:

1. **The premise aged out.** API prompt caching now handles most of the *cost*
   side — re-sending a long history is cheap on a cache hit. Saving tokens was
   no longer the interesting problem.
2. **The design depended on the model remembering.** Capture required the
   assistant to call a logging tool after every single exchange. Models drift.
   Turns went missing, buffers developed holes, and the summary cycle often
   never fired at all.

## What replaced it

[**Session Continuity**](https://github.com/tkovacs9520-alt/sapphire-session-continuity)
rebuilds the idea on Sapphire's hook system and aims at the half caching
*doesn't* solve — context size:

- Capture is **automatic** via a `post_chat` hook. No model memory required.
- Compression is prompted through `ghost_inject`, which is ephemeral and
  cache-friendly rather than cache-breaking.
- Buffers are **chat-scoped** and never touch the core memory system.
- Hooks are withheld in private chats by design.

It matters most on local models, which have no prompt caching and small context
windows.
