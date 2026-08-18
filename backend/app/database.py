import socket
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # 长任务（内容/图审核纯 LLM 阶段可达数分钟）期间连接在池中空闲，
    # 若中间层（NAT/防火墙，常见 ~300s 空闲超时）回收连接，下次查询会
    # Lost connection(2013) during query。recycle 缩短到 240s，让空闲
    # 连接在超时前主动重建（配合 pool_pre_ping 双保险）。
    pool_recycle=240,
    pool_timeout=15,
    connect_args={
        "connect_timeout": 10,
        "read_timeout": 120,
        "write_timeout": 120,
    },
)


@event.listens_for(engine, "connect")
def _enable_tcp_keepalive(dbapi_conn, connection_record) -> None:
    """新连接开启 TCP keepalive：空闲时定期发探测包，避免被中间层
    当作死连接回收。Linux/BSD 下同时设置空闲 120s 后每 30s 探测；
    Windows 无 TCP_KEEPIDLE 常量（探测间隔走系统默认），尽力而为。"""
    try:
        sock = dbapi_conn._sock  # pymysql 底层 socket
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt in ("TCP_KEEPIDLE", "TCP_KEEPINTVL", "TCP_KEEPCNT"):
            val = {"TCP_KEEPIDLE": 120, "TCP_KEEPINTVL": 30, "TCP_KEEPCNT": 3}[opt]
            opt_const = getattr(socket, opt, None)
            if opt_const is None:
                continue
            try:
                sock.setsockopt(socket.IPPROTO_TCP, opt_const, val)
            except OSError:
                pass
    except Exception:
        # 连接初始化阶段的 socket 探活失败不应影响连接本身
        pass


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
