# B01PDF

윈도우용 간단한 설치형 PDF 뷰어. PDF는 로컬에서 처리하며 네트워크 요청, 업로드, 광고, 추적 기능이 없습니다.

## 기능

- 100% 기본 배율, 10-400% 확대·축소, Fit Width / Fit Page
- 1장, 2장(1-2, 3-4 순), 연속 스크롤 보기
- 왼쪽 페이지 미리보기, 클릭 이동, F9로 사이드바 표시 전환
- 원본 / 선명하게(Unsharp Mask) / 부드럽게(1.5배 렌더 후 축소) 필터
- '닫은 페이지 위치 기억하기' 설정: 파일별 페이지, 스크롤 위치, 배율과 보기 모드 복원
- PDF 끌어 놓기, 암호 입력, 명령줄 파일 열기

## 설치

[Actions](https://github.com/BE0X01/B01PDF/actions) → 최신 성공한 'Windows installer' 실행 → Artifacts → `B01PDF-Windows-Setup` 다운로드 → 압축 해제 → `B01PDF-Setup.exe` 실행.

관리자 권한이나 별도 Python 설치 없이 사용자 폴더에 설치됩니다. Portable는 압축 해제 후 폴더 전체를 유지하고 `B01PDF.exe`로 실행합니다. 초기 버전은 코드 서명이 없습니다.

## 개발

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
```

Ctrl+O: 열기 / Ctrl+0: 100% / Ctrl+플러스·마이너스 또는 Ctrl+휠: 배율 / Page Up·Down: 페이지 이동.

100%는 PDF 1포인트를 96/72 논리 픽셀로 표시합니다. OS 배율이 적용되므로 종이 실측 크기와 같다는 의미는 아닙니다. '원본'도 PDF 엔진의 기본 안티앨리어싱을 사용하며, '부드럽게'는 추가 슈퍼샘플링을 적용합니다. 이미지 필터는 화면 표시에만 적용하고 PDF 파일을 변경하지 않습니다.

설정은 Windows 사용자 레지스트리 `HKEY_CURRENT_USER\Software\B01\B01PDF`에 저장됩니다. 위치 기억을 끄면 기존 위치 기록을 지우며 이후 저장·복원하지 않습니다. 파일 이동이나 이름 변경은 새로운 파일로 취급합니다.

현재 범위는 읽기 전용 이미지 렌더링입니다. 텍스트 선택·검색, 주석, 인쇄, 편집은 포함하지 않습니다. 보이는 페이지에 대해서만 렌더링하며 캐시는 96 MiB, 개별 렌더는 12메가픽셀로 제한합니다. 복잡한 PDF 렌더링은 UI 스레드에서 이루어져 잠시 멈출 수 있습니다.

## 사용한 라이브러리

PySide6 / Qt PDF와 Pillow. 라이선스 안내는 [THIRD_PARTY.md](THIRD_PARTY.md)를 참고하세요.
