"""Serve a single app on explicitly selected lab HTTP ports with shared caches."""

import asyncio
import os
import socket

import uvicorn


async def serve():
    ports = list(dict.fromkeys(int(p) for p in os.getenv("POND_HTTP_PORTS", "8000").split(",")))
    sockets = []
    try:
        for port in ports:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(("0.0.0.0", port))
            except OSError:
                listener.close()
                raise
            listener.listen(128)
            listener.setblocking(False)
            sockets.append(listener)
        config = uvicorn.Config("web:create_app", factory=True, proxy_headers=False)
        await uvicorn.Server(config).serve(sockets=sockets)
    finally:
        for listener in sockets:
            listener.close()


if __name__ == "__main__":
    asyncio.run(serve())
