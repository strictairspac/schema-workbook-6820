import os
DATABASE_URL=os.getenv('DATABASE_URL','mysql+pymysql://schemaworkbook:schemaworkbook_demo_pw@localhost:17743/schemaworkbook')
# 分解报告查询专用的只读从库；未配置时回退主库，行为与单库部署一致。
DATABASE_REPLICA_URL=os.getenv('DATABASE_REPLICA_URL','').strip()
REDIS_URL=os.getenv('REDIS_URL','redis://redis:6379/0')
JWT_SECRET=os.getenv('JWT_SECRET','local-schema-workbook-change-before-public-use')
