# Purpose: 견본 모듈 demo_crash 의 화면 — 서버에 없는 패키지를 불러 import 실패 격리를 보인다.

import importlib

from capa_simulation import module_api as api

ctx = api.context(__file__)
api.page_header(ctx, "패키지 없음 데모")
importlib.import_module("demo_not_installed_package")
