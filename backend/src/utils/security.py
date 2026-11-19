import hashlib,hmac,os,jwt
from datetime import datetime,timedelta,timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from src.config.settings import JWT_SECRET
from src.config.database import db_session
from src.models.entities import User
from src.constants.enums import ROLES
bearer=HTTPBearer()

class TokenUser:
    """主库中断时由已签名令牌还原的只读身份。"""
    def __init__(self,payload):
        self.id=int(payload['sub']);self.email=payload.get('email','');self.role=payload.get('role','')
    def __getattr__(self,name): raise AttributeError(name)

def password_hash(value,salt=None):
    salt=salt or os.urandom(16).hex()
    return salt+':'+hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),180000).hex()
def check_password(value,encoded): return hmac.compare_digest(password_hash(value,encoded.split(':')[0]),encoded)
def issue(user): return jwt.encode({'sub':str(user.id),'email':user.email,'role':user.role,'exp':datetime.now(timezone.utc)+timedelta(hours=8)},JWT_SECRET,algorithm='HS256')
def current(token=Depends(bearer),db=Depends(db_session)):
    try:
        payload=jwt.decode(token.credentials,JWT_SECRET,algorithms=['HS256'])
        try:
            user=db.get(User,int(payload['sub']))
            if not user or user.role not in ROLES: raise ValueError()
            return user
        except OperationalError:
            # 主库中断：令牌本身已签名，降级为令牌声明身份，保证已追上进度的只读会话可查。
            db.rollback()
            if payload.get('role') in ROLES and payload.get('email'): return TokenUser(payload)
            raise
    except HTTPException: raise
    except OperationalError: raise HTTPException(503,'主库暂时不可用，请稍后重试')
    except Exception: raise HTTPException(401,'登录已过期，请重新登录')
def writer(user=Depends(current)):
    if user.role not in ('operator','admin'): raise HTTPException(403,'观察员仅可查看和导出')
    return user
def admin(user=Depends(current)):
    if user.role!='admin': raise HTTPException(403,'仅管理员可访问审计')
    return user
