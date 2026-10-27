[README.md](https://github.com/user-attachments/files/34050812/README.md)
# Geun's Stock Screener

미너비니(Mark Minervini)의 트렌드 템플릿·진입모델(VCP, 컵 위드 핸들, 3C, 플랫 베이스, 파워 플레이)을 바탕으로 한 개인용 국내 주식 스크리너입니다.

평일 장 마감 후(16:40)에 국내 전 종목을 자동으로 스크리닝하고, 그 결과를 웹사이트로 보여줍니다.
비용은 무료입니다(GitHub Actions + GitHub Pages). 무료 계정에서는 사이트가 공개됩니다.

## 설정 (처음 한 번, 약 20~30분)

1. https://github.com 에서 무료로 가입하고 로그인합니다.
2. 오른쪽 위 **+ → New repository**를 누르고 이름(예: `geuns-stock-screener`, 저장소 이름에는 작은따옴표를 쓸 수 없습니다)을 입력합니다. **Public**을 선택하고 **Create repository**를 누릅니다.
3. 새 저장소 화면에서 **uploading an existing file**을 누릅니다. 압축을 푼 폴더 **안의 내용 전체**(`docs`, `screener`, `.github`, `pine`, `requirements.txt`, `README.md`)를 끌어다 놓고 **Commit changes**를 누릅니다.
   - `.github` 폴더는 숨김 폴더라 보이지 않을 수 있습니다. 윈도우는 탐색기 → 보기 → 숨긴 항목, 맥은 Finder에서 `Cmd+Shift+.`을 누르세요.
   - 끌어다 놓기로 `.github`가 올라가지 않으면 저장소에서 **Add file → Create new file**을 누르고, 이름 칸에 `.github/workflows/screener.yml`을 입력한 뒤 같은 파일의 내용을 붙여 넣으세요.
4. **Settings → Actions → General**로 가서 맨 아래 **Workflow permissions**를 **Read and write permissions**로 바꾸고 저장합니다.
5. **Settings → Pages**로 가서 Source는 **Deploy from a branch**, Branch는 **main**, 폴더는 **/docs**를 선택하고 저장합니다.
6. **Actions** 탭 → **daily-screener** → **Run workflow**를 눌러 첫 실행을 합니다. 1~3분이면 끝나고 초록색 체크가 뜹니다.
7. 1~2분 뒤 `https://<내아이디>.github.io/geuns-stock-screener/` 에 접속합니다.

이후에는 평일마다 자동으로 갱신됩니다. 장이 쉬는 날에는 직전 거래일 결과가 그대로 유지됩니다.

## 사이트 기능
- 시장 판단(코스피200·코스닥150 ETF 기준), 분석 종목 수, 트렌드 템플릿 통과 수, VCP 후보 수
- VCP 후보 / 트렌드 템플릿 전체 표: 열 제목을 누르면 정렬됩니다. 실적 등급, 피벗, 손절가, 손절폭, 매수 수량도 표시합니다.
- 계좌 금액과 1회 리스크(%)를 입력하면 1R 기준 매수 수량이 바로 계산됩니다.
- 종목을 누르면 캔들 차트, 50·150·200일선, 피벗선, 손절선이 나오고 **TradingView에서 열기** 버튼이 있습니다.
- **TradingView 관심목록 받기**로 받은 txt는 TradingView 관심목록 메뉴(⋯) → **목록 가져오기**로 불러올 수 있습니다.
- 위쪽 날짜 선택에서 지난 결과(최근 60거래일)를 볼 수 있습니다.

## 설정 바꾸기
- 조건값: `screener/run_tv.py`의 `SETTINGS`(시가총액, 거래대금, RS 기준)와 `screener/vcp.py`의 `CFG`(VCP 기준)
- 실행 시각: `.github/workflows/screener.yml`의 `cron`. 시간은 UTC 기준이라 한국 시간에서 9시간을 빼야 합니다.

## 문제 해결
- **Actions가 빨간 X로 실패할 때:** 실패한 실행을 눌러 로그를 확인하세요. `TradingView 스크리너 조회 실패`라고 나오면 TradingView 쪽 일시 차단일 수 있으니, 다음 날 다시 확인하세요. 차트 데이터 다운로드 실패라면 GitHub 서버(해외)에서 접속이 막혔을 수 있습니다. 로그를 그대로 복사해서 보내 주시면 고쳐 드리겠습니다.
- **push 권한 오류가 날 때:** 설정 4번을 다시 확인하세요.
- **사이트가 404일 때:** 설정 5번 후 몇 분 기다리세요. 주소 끝에 `/`를 붙여 보세요.

## 주의
- `tradingview-screener`는 TradingView가 공식으로 제공하는 API가 아닙니다. 사이트 구조가 바뀌면 멈출 수 있으니 개인용으로 하루 한 번 정도만 쓰세요.
- 실적 등급은 최근 분기의 전년 대비 증가율(매출, EPS)로만 매깁니다. 최종 확인은 DART 원문 공시로 하세요.
- 기계적으로 걸러낸 결과이며 매수 추천이 아닙니다.

## 모의투자 기록 (v3 추가)

- `screener/tracker.py`가 매일 실행 때 "진입 신호 확인"·"패턴 형성 중" 종목을 기록하고, 이후 진입·청산을 자동 추적합니다.
- 저장 위치: `docs/data/forward/ledger.json`, `ledger.csv` (자동 실행이 `docs/data`를 커밋하므로 저장소에 누적됩니다).
- 규칙은 `screener/config.json`의 `forward` 항목. **기록이 쌓이는 중에는 바꾸지 마세요** (전후 비교가 깨집니다).
- **주의:** 수정본을 올릴 때 저장소의 `docs/data/forward` 폴더를 덮어쓰거나 지우면 누적 기록이 사라집니다.
- 사이트의 "모의투자 기록" 탭에서 요약·모델별 성과·전체 기록을 볼 수 있습니다. 청산 30건 미만에서는 성과를 판단하지 마세요.

## 기존 사이트(미너비니 스크리너)에서 옮겨 올 때

- 새 저장소에서 첫 실행이 성공하면, **기존 저장소의 Actions는 꺼 두세요** (Actions → daily-screener → 오른쪽 ⋯ → Disable workflow). 두 저장소가 같은 시각에 TradingView를 조회하면 차단 위험이 커집니다.
- 기존 저장소에 이미 모의투자 기록(`docs/data/forward/ledger.json`, `ledger.csv`)이 쌓여 있다면, 두 파일을 새 저장소의 같은 위치(`docs/data/forward/`)에 올리면 기록이 이어집니다. 없으면 새 저장소에서 처음부터 쌓입니다.
- 기존 저장소는 확인이 끝날 때까지 지우지 말고 남겨 두세요.
