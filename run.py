import sys
import asyncio

# Must be set BEFORE uvicorn imports its loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,       # ✅ reload=False — reloader spawns a child process
                            #    that resets the event loop policy
        loop="asyncio"
    )