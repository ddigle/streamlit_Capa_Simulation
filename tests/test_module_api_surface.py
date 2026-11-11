# Purpose: 모듈 공개 창구 module_api v1 의 겉면(이름·서명·칸·키와 주소 꼴·색 키)을 고정한다.

"""모듈 공개 창구 겉면.

사외는 모듈을 볼 수 없다. 창구가 깨지는 것을 사외 관문에서 잡는 길은 이 시험과 견본
(`tests/fixtures/modules/demo_ok`)뿐이다. **아래 기대 글자를 바꾸는 변경은 호환 정책(AGENTS
12장 「코어 공개 창구 변경」, 사양 3-3)을 따른다** — 더하기만 하는 변경은 작은 판(`API_MINOR`)을
올리고 지침서 부록 C 「창구 변경 기록」 에 한 줄을 적는다. 지우기·이름 바꾸기·서명 바꾸기·뜻
바꾸기는 큰 판을 올리고 옛 큰 판을 남긴다. 이름·서명을 그대로 두고 인자를 폐기 예정으로 받기만
하거나 화면에 그리는 것만 줄이는 변경은 작은 판이다(창구 1.1 · 1.2). 기대 글자를 고칠 때는 둘
가운데 어느 쪽인지 커밋에 적는다.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from capa_simulation import module_api, module_failures, module_registry
from capa_simulation.design import theme, tokens

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_OK = PROJECT_ROOT / "tests" / "fixtures" / "modules" / "demo_ok"
DEMO_OK_PAGE = DEMO_OK / "demo_ok_page.py"

EXPECTED_ALL = [
    "API_VERSION",
    "FONT_FAMILY",
    "IMPLEMENTING_SUFFIX",
    "PALETTE_KEYS",
    "S3_MAX_BYTES",
    "BigDataQueryError",
    "ModuleContext",
    "ModuleContextError",
    "S3Result",
    "context",
    "page_header",
    "palette",
    "query_bigdataquery",
    "s3_download",
    "s3_upload",
]
EXPECTED_SIGNATURES = {
    "context": "(file: 'str | os.PathLike[str]') -> 'ModuleContext'",
    "page_header": (
        "(ctx: 'ModuleContext', title: 'str', *, description: 'str | None' = None) -> 'None'"
    ),
    "palette": "() -> 'Mapping[str, str]'",
    "query_bigdataquery": (
        "(ctx: 'ModuleContext', sql: 'str', *, start: 'date | None' = None, "
        "end: 'date | None' = None) -> 'pd.DataFrame'"
    ),
    "s3_upload": "(ctx: 'ModuleContext', name: 'str') -> 'S3Result'",
    "s3_download": "(ctx: 'ModuleContext', name: 'str') -> 'S3Result'",
    "BigDataQueryError": "(kind: 'str', message: 'str') -> 'None'",
    "ModuleContext.key": "(self, name: 'str') -> 'str'",
    "ModuleContext.callback": ("(self, fn: 'Callable[..., object]') -> 'Callable[..., None]'"),
    "ModuleContext.guard": "(self) -> 'AbstractContextManager[None]'",
}
EXPECTED_FIELDS = ["id", "name", "owner", "maturity", "folder", "api_version"]
EXPECTED_RESULT_FIELDS = ["ok", "reason", "detail", "size"]
EXPECTED_PALETTE_KEYS = (
    "surface",
    "surface_subtle",
    "border",
    "text",
    "text_muted",
    "accent",
    "secure",
    "warning",
    "shortage",
)
PALETTE_TOKENS = {
    "surface": "SURFACE",
    "surface_subtle": "SURFACE_SUBTLE",
    "border": "BORDER",
    "text": "TEXT",
    "text_muted": "TEXT_MUTED",
    "accent": "ACCENT",
    "secure": "STATUS_SECURE",
    "warning": "STATUS_WARNING",
    "shortage": "STATUS_SHORTAGE",
}


def test_the_public_names_are_exactly_the_v1_surface() -> None:
    assert module_api.__all__ == EXPECTED_ALL
    for name in EXPECTED_ALL:
        assert hasattr(module_api, name), name


def test_no_public_name_outside_the_surface_reaches_into_the_core() -> None:
    """`__all__` 밖의 공개 이름으로 코어에 닿지 않는다 — `api.module_registry.settings.DUCKDB_PATH`
    같은 길이 서면 「데이터는 내지 않는다」 가 이름뿐이 된다. 코어 이름은 `_` 별명으로만 들인다."""

    def core_origin(value: object) -> str:
        if inspect.ismodule(value):
            return value.__name__
        return str(getattr(value, "__module__", "") or "")

    leaks = sorted(
        name
        for name, value in vars(module_api).items()
        if not name.startswith("_")
        and name not in EXPECTED_ALL
        and core_origin(value).startswith("capa_simulation")
    )

    assert not leaks, leaks


def test_every_public_signature_is_pinned() -> None:
    found = {
        "context": str(inspect.signature(module_api.context)),
        "page_header": str(inspect.signature(module_api.page_header)),
        "palette": str(inspect.signature(module_api.palette)),
        "query_bigdataquery": str(inspect.signature(module_api.query_bigdataquery)),
        "s3_upload": str(inspect.signature(module_api.s3_upload)),
        "s3_download": str(inspect.signature(module_api.s3_download)),
        "BigDataQueryError": str(inspect.signature(module_api.BigDataQueryError)),
        "ModuleContext.key": str(inspect.signature(module_api.ModuleContext.key)),
        "ModuleContext.callback": str(inspect.signature(module_api.ModuleContext.callback)),
        "ModuleContext.guard": str(inspect.signature(module_api.ModuleContext.guard)),
    }

    assert found == EXPECTED_SIGNATURES
    # 속성 둘은 읽기 전용 property 다.
    for name in ("key_prefix", "data_dir"):
        member = inspect.getattr_static(module_api.ModuleContext, name)
        assert isinstance(member, property) and member.fset is None, name


def test_the_helper_result_and_failure_shapes_are_pinned() -> None:
    """도우미(창구 1.3)의 결과 칸 · 실패 꼴 · 상한 — 모듈이 `reason` · `kind` 로 가른다."""
    assert [field.name for field in dataclasses.fields(module_api.S3Result)] == (
        EXPECTED_RESULT_FIELDS
    )
    result = module_api.S3Result(ok=False, reason="쓸 수 없음")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ok = True  # type: ignore[misc]
    assert issubclass(module_api.BigDataQueryError, RuntimeError)
    assert module_api.BigDataQueryError("입력", "글").kind == "입력"
    assert module_api.S3_MAX_BYTES == 8 * 1024 * 1024


def test_the_context_fields_and_their_order_are_pinned_and_frozen() -> None:
    assert [field.name for field in dataclasses.fields(module_api.ModuleContext)] == EXPECTED_FIELDS
    context = module_api.context(DEMO_OK_PAGE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.id = "other"  # type: ignore[misc]


def test_the_key_and_address_shapes_are_pinned() -> None:
    """주소는 북마크되고 키는 세션에 남는다 — 꼴을 바꾸면 기존 북마크·세션이 끊긴다."""
    context = module_api.context(DEMO_OK_PAGE)

    assert module_registry.key_prefix("demo_ok") == "mod_demo_ok__"
    assert module_registry.page_url_path("demo_ok", "main") == "mod-demo_ok-main"
    assert context.key_prefix == "mod_demo_ok__"
    assert context.key("x") == "mod_demo_ok__x"
    assert module_failures.callback_failure_key("demo_ok") == "mod_demo_ok___core_callback_failure"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_palette_keys_are_pinned_in_both_themes(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setattr(theme._LOCAL, "mode", mode, raising=False)

    assert module_api.PALETTE_KEYS == EXPECTED_PALETTE_KEYS
    colors = module_api.palette()
    assert tuple(colors) == EXPECTED_PALETTE_KEYS
    assert dict(colors) == {
        key: tokens.palette_value(mode, name) for key, name in PALETTE_TOKENS.items()
    }


def test_the_core_supports_its_own_api_version() -> None:
    assert module_api.API_VERSION == (module_registry.API_MAJOR, module_registry.API_MINOR)
    assert module_api.API_VERSION[0] in module_registry.SUPPORTED_API_MAJORS
    assert module_api.IMPLEMENTING_SUFFIX == "(구현중)"
    assert module_api.FONT_FAMILY == tokens.FONT_FAMILY


def test_the_demo_ok_fixture_uses_every_public_name() -> None:
    """견본이 겉면 전부를 쓴다 — 코어가 창구를 깨면 견본 AppTest 와 이 시험이 떨어진다."""
    tree = ast.parse(DEMO_OK_PAGE.read_text(encoding="utf-8"))
    used = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "api"
    }
    context_members = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ctx"
    }

    assert set(EXPECTED_ALL) <= used, set(EXPECTED_ALL) - used
    assert {"key", "data_dir", "callback", "guard"} <= context_members
