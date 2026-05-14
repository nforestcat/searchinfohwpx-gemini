---
name: search-info-hwpx
description: "주제별 주간동향 HWPX 보고서 자동 생성. 서브에이전트 병렬 검색 → JSON 추출/중복제거 → HWPX 빌드. 트리거: '주간동향', '동향 hwpx', 'weekly report', '{주제} 동향'."
---

# Search Info HWPX — 주제별 주간동향 HWPX 보고서

임의의 주제에 대해 논문/뉴스/특허를 병렬 검색하고, 중복을 제거한 뒤, HWPX 동향 보고서를 자동 생성하는 통합 스킬.

## 입력 파라미터

| 파라미터 | 필수 | 설명 | 예시 |
|---------|------|------|------|
| `주제` (topic) | Yes | 동향 조사 주제 | "휴머노이드", "AI for Science", "양자컴퓨팅" |
| `기간` (period) | No | 검색 기간 (기본: 8일) | "2주", "1개월", "8days" |
| `출력폴더` (output_dir) | No | 이번 실행의 출력 경로 (미지정 시 config 값 사용) | "C:/output" |
| `--no-zotero` | No | Zotero 등록 건너뛰기 | |

사용자가 주제를 전달한다. 누락 시 반드시 물어본다.

## 초기 설정 (Phase 0)

`config.json`이 없으면 **첫 실행 시 사용자에게 설정을 물어본다**.

**config.json 경로**: `{이 스킬 디렉토리}/config.json`

**필수 설정 (config.json):**

```json
{
  "hwpx_template": "C:/path/to/양식.hwpx",
  "output_dir": "C:/path/to/output/"
}
```

- `hwpx_template`: HWPX 양식 파일(.hwpx) 경로
- `output_dir`: 출력 파일을 저장할 기본 디렉토리 경로

`ask_user`로 정보를 수집한 후 `write_file`로 저장한다.

## 워크플로우

### Phase 1: 준비 및 키워드 전략

1. **config.json 로드** — 없으면 Phase 0(초기 설정) 실행
2. **날짜 계산**: 오늘 날짜 및 `DATE_CUTOFF` (기본 8일 전) 계산
3. **키워드 자동 생성**: 메인 에이전트는 주제를 분석하여 검색용 키워드(국문/영문), 주요 기업, 핵심 기술 용어를 도출한다.

### Phase 2: 서브에이전트 병렬 검색 (invoke_agent)

`invoke_agent`를 사용하여 3개의 작업을 **병렬로 실행**한다(`wait_for_previous: false`). 각 서브에이전트에게는 `google_web_search`와 `web_fetch`를 사용하여 최신 정보를 수집하고 반드시 지정된 JSON 포맷으로 응답할 것을 명령한다.

| 작업명 (Sub-agent) | 검색 타겟 및 지침 |
|:---|:---|
| **paper-searcher** | arXiv, ScienceDirect, RSC, ACS, MDPI 등. **연구 수행 기관(Affiliation)**을 식별하여 `source` 필드에 '기관명 (학술지명)' 형식으로 기재. |
| **news-searcher** | 주요 기술 매체 및 공식 보도자료. 동향의 주체(기업) 식별에 집중. |
| **patent-searcher** | Google Patents 등 최신 특허. 출원인 정보를 `source` 필드에 매핑. |

**서브에이전트 전달 JSON 포맷:**
```json
[
  {
    "source": "연구기관(학술지) 또는 기업명",
    "title_en": "Original English Title",
    "title": "한국어 번역 제목",
    "date": "YYYY-MM-DD",
    "url": "Direct Detailed URL (DOI/Article Page)",
    "summary": "한국어 요약 (최소 3-4문장. 첫 문장은 핵심 요약, 이후는 기술적/비즈니스 상세 내용)",
    "type": "paper|news|patent"
  }
]
```

### Phase 3: JSON 추출 및 중복 제거 (Defensive Parsing)

서브에이전트의 응답을 취합할 때 다음 **방어 로직**을 적용한다:

1. **JSON 추출 (Defensive Parsing)**: 
   - 응답 텍스트에서 ` ```json ` 및 ` ``` ` 마크다운 블록을 찾아 그 내부의 컨텐츠만 추출한다.
   - 블록이 없을 경우, 텍스트 내 첫 번째 `[`와 마지막 `]` 사이의 내용을 추출하여 파싱을 시도한다.
   - 파싱 실패 시, 서브에이전트에게 재시도를 요청하거나 해당 응답을 제외하고 로그를 남긴다.

2. **중복 제거 및 정제**:
   - **URL 기준**: 동일 URL은 1건만 유지 (더 상세한 요약 선택).
   - **유사도 기준**: 영문 제목(title_en) 정규화 후 유사도 80% 이상 시 동일 건 간주.
   - **내용 기준**: 공식 발표/논문 > 전문매체 > 일반매체 순으로 우선순위 부여.
   - **정제**: `DATE_CUTOFF` 이전 데이터 삭제, 날짜 내림차순 정렬.
   - 결과물을 `_workspace/processed_items.json`에 저장한다.

### Phase 4: HWPX 빌드 및 후처리 (run_shell_command)

로컬의 Python 스크립트를 `run_shell_command`로 순차 실행한다. 환경 변수 `PYTHONUTF8=1`을 반드시 접두어로 사용한다.

1. **빌드**: `scripts/build_hwpx.py` 실행 (내부적으로 `hp:linesegarray`를 제거하여 자동 레이아웃 보장)
   ```bash
   PYTHONUTF8=1 python "scripts/build_hwpx.py" --template "{template}" --output "{output}" --data "_workspace/processed_items.json" --today "YY.MM.DD" --title "동적 제목"
   ```
2. **네임스페이스 수정**: `scripts/fix_namespaces.py` 실행
3. **유효성 검증**: `scripts/validate.py` 실행

### Phase 5: 요약 및 결과 출력

최종 생성된 파일 경로, 수집된 건수(뉴스/논문/특허별), 중복 제거된 건수, Zotero 등록 여부를 요약하여 출력한다.

---

## 핵심 지침 (Operational Rules)

1. **병렬 실행**: Phase 2의 검색 단계에서 도구의 병렬 실행 능력을 최대한 활용한다.
2. **데이터 품질**: 
   - `source`: 단순 언론사/출판사가 아닌 기술 동향의 실제 주체(연구소/회사)를 명시한다. 논문은 '기관명 (저널명)' 형식을 권장한다.
   - `url`: 홈페이지 주소가 아닌, 해당 정보의 **상세 페이지(DOI 링크 등) 다이렉트 주소**를 반드시 수집한다.
   - `summary`: 반드시 명사형/음슴체(~함, ~임, ~달성)로 작성하되, 양식의 '상세설명' 칸을 채울 수 있도록 **3문장 이상의 충분한 분량**을 확보한다.
3. **사실 확인 (Fact-Check)**: 존재하지 않는 가공된 링크나 허위 사실이 포함되지 않도록 검색 결과를 엄격히 검증한다.
4. **오류 처리**: 스크립트 실행 실패 시 에러 메시지를 분석하여 가능한 경우 수정한 뒤 재시도한다.
5. **레이아웃 보장**: 고정된 줄 정보(`hp:linesegarray`)를 제거하여 HWP 뷰어에서 자간/장평이 뭉치지 않고 자동 줄바꿈되도록 한다.
6. **인코딩 보장**: 모든 Shell 명령 실행 시 `PYTHONUTF8=1`을 명시하여 한글 처리 오류를 방지한다.
