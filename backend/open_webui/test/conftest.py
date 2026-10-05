"""AI4BI: cô lập môi trường cho mọi test backend.

Import open_webui.config (kéo theo từ middleware, routers…) sẽ:
  - xoá tệp cấp đầu trong STATIC_DIR (mặc định open_webui/static, có trong git) rồi chép lại;
  - chạy alembic upgrade trên DATABASE_URL (mặc định backend/data/webui.db — DB dev thật);
  - tạo vector DB trong DATA_DIR.
Tệp này chạy trước mọi module test nên ép các đường dẫn đó vào thư mục tạm, bỏ biến trỏ tới DB
thật. Nhờ vậy chạy `python -m pytest` trực tiếp cũng an toàn, không cần scripts/test.sh.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix='owui-test-'))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

for _name in (
    'DATABASE_URL',
    'DATABASE_TYPE',
    'DATABASE_HOST',
    'DATABASE_PORT',
    'DATABASE_NAME',
    'DATABASE_USER',
    'DATABASE_PASSWORD',
    'REDIS_URL',
    'VECTOR_DB',
):
    os.environ.pop(_name, None)

for _name in ('data', 'static', 'frontend'):
    (_TMP / _name).mkdir()

os.environ['DATA_DIR'] = str(_TMP / 'data')
os.environ['STATIC_DIR'] = str(_TMP / 'static')
os.environ['FRONTEND_BUILD_DIR'] = str(_TMP / 'frontend')
os.environ['WEBUI_SECRET_KEY'] = 'test'
os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['DO_NOT_TRACK'] = 'true'
os.environ['SCARF_NO_ANALYTICS'] = 'true'
