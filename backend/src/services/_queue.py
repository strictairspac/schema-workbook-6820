from redis import Redis
from src.config.settings import REDIS_URL
queue=Redis.from_url(REDIS_URL,decode_responses=True)
