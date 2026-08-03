# Capa Simulation

Excel 2021 `.xlsb` 기준정보를 `xlwings`로 읽고, HBM PKG 라인의 월별 부하량,
소요대수, 확보율 및 병목 공정을 계산하는 Streamlit 프로젝트입니다.

## 권장 실행 환경

- Windows 10/11
- Microsoft Excel 2021 또는 Microsoft 365 Desktop
- Python 3.10.11 64-bit
- Git for Windows

## 초기 설정

```powershell
py -3.10 --version
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

PowerShell에서 가상환경 스크립트 실행이 차단되면 현재 사용자 범위의 실행 정책을
확인한 후 조직 보안 정책에 맞게 설정해야 합니다.

## 실행

```powershell
streamlit run app.py
```

## 검사

```powershell
pytest
ruff check .
ruff format --check .
```

## 데이터 관리

- 실제 Excel 파일은 `data/input/`에 두며 Git에 포함하지 않습니다.
- 생성 결과는 `data/output/`에 저장하며 Git에 포함하지 않습니다.
- 구조 공유가 필요하면 민감정보를 제거한 샘플 파일이나 CSV 스키마를
  `data/sample/`에 추가합니다.
- `.streamlit/secrets.toml`과 `.env`는 로컬 전용입니다.
