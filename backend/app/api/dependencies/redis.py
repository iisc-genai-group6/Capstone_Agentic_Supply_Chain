from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis


def get_redis_client(request: Request) -> Redis:
    return request.app.state.container.redis_client()


RedisDep = Annotated[Redis, Depends(get_redis_client)]
