# 엑시콘 기업분석 Phase 2 — 소스로그와 원자료 구축 결과

> 실행 기준: 2026-08-13 17:07:42 KST 최종 재수집  
> 공시 컷오프: 2026-08-13 16:00 KST  
> 회사 식별자: 엑시콘(092870), OpenDART `corp_code=00611736`  
> 실행 스크립트: `scripts/collect_opendart_phase2.ps1`, `scripts/normalize_opendart_phase2.py`  
> 관련 로그: `LOG-20260813-015`~`020`

## 1. 단계 결론

Phase 2의 데이터 계층은 완료했다. OpenDART API를 통해 공시 목록, 연결·별도 재무제표, 주식·자기주식·자본변동·최대주주 자료, 2026년 공시 19건과 2023년 이후 정기보고서 원문을 수집했고, 원문과 정규화 결과를 SHA-256으로 추적할 수 있게 만들었다.

| 완료 항목 | 결과 |
|---|---:|
| OpenDART 저장 데이터셋 | 124개, 전부 `status=000` |
| 실제 API 호출 | 125회; 2023년 이후 공시목록이 2페이지라 데이터셋 수보다 1회 많음 |
| 2023-01-01~2026-08-13 공시 | 119건 전수 저장 |
| 2026-01-01~2026-08-13 공시 | 19건 전수 저장 |
| 재무제표 | 13개 기간 × `CFS`·`OFS` = 26개 페이로드, 3,129행 |
| 주식·주주·자본 자료 | 13개 기간 × 5개 API = 65개 페이로드, 673행 |
| 핵심 공시 원문 | 중복 제거 30개 ZIP·30개 추출 XML; 2026년 19건과 재무 13기간 전부 포함 |
| 계약 공시 | 원문 6건 → 고유 계약 5건 → 2026년 신규 4건 |
| 2026년 신규 계약 합계 | 101,801,700,000원 = 1,018.017억원 |
| 자동 검산 | 194개 통과, 실패 0개 |

계획서의 Phase 2 완료 기준인 ‘핵심 숫자를 원문까지 추적할 수 있다’는 충족했다. 다만 계획된 `01_엑시콘_소스로그.xlsx` 포장은 현재 세션에 전용 스프레드시트 런타임과 의존성 로더가 제공되지 않아 생성하지 않았다. 대체 라이브러리로 우회하지 않고, 같은 내용을 이 문서와 정규화 JSON으로 보존했다.

## 2. 데이터 흐름과 재현 방법

```text
.env의 DART_API_KEY (Git 제외, 값 비기록)
  → OpenDART JSON·원문 ZIP 호출
  → raw/dart의 원응답 저장
  → run_manifest.json에 endpoint·비밀값 제외 파라미터·시각·행수·SHA-256 기록
  → 원문 XML·재무·주식 데이터 정규화
  → normalized/*.json
  → checks.json의 194개 검산
  → Phase 3 Historical·계약 모델 입력
```

재현 명령은 다음 두 개다. 인증키는 명령이나 결과에 출력되지 않는다.

```powershell
& .\scripts\collect_opendart_phase2.ps1
python .\scripts\normalize_opendart_phase2.py
```

주요 추적 파일은 다음과 같다.

- 원수집 매니페스트: [`raw/dart/run_manifest.json`](raw/dart/run_manifest.json)
- 정규화 매니페스트: [`raw/dart/normalized/normalization_manifest.json`](raw/dart/normalized/normalization_manifest.json)
- 전체 검산: [`raw/dart/normalized/checks.json`](raw/dart/normalized/checks.json)
- 연결 핵심 계정: [`raw/dart/normalized/key_financials_cfs.json`](raw/dart/normalized/key_financials_cfs.json)
- 계약 원장: [`raw/dart/normalized/contracts.json`](raw/dart/normalized/contracts.json)
- 공시 요약: [`raw/dart/normalized/disclosures_summary.json`](raw/dart/normalized/disclosures_summary.json)

`raw/`와 `.env`는 `.gitignore`에 포함돼 있다. 원수집 매니페스트는 API 키를 제외한 요청 파라미터만 저장하며 `api_key_logged=false`를 명시한다.

## 3. Phase 1 OpenDART 재검증

### 3.1 회사·최신 정기공시

- `/company.json`: `status=000`, 회사명 `(주)엑시콘`, 종목코드 `092870`
- `/list.json`, 2026-01-01~2026-08-13: `status=000`, 총 19건
- 최신 정기보고서: [2026년 1분기보고서, DART `20260515001551`](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260515001551)
- 2026년 반기보고서: 컷오프 기준 0건

따라서 Phase 1의 최신 정기보고서는 1분기보고서이며 반기보고서는 미제출이라는 판정은 API로도 재현됐다.

### 3.2 DART 19건과 KIND 23건의 차이

KIND의 같은 기간 23건 중 OpenDART에 없는 4건은 엑시콘 제출 공시가 아니라 KRX 시장감시위원회의 투자주의 지정이다.

| 일시 | KIND 접수번호 | 시장조치 |
|---|---:|---|
| 2026-02-03 20:02 | [20260203001040](https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20260203001040&docno=&viewerhost=&viewerport=) | 15일간 상승종목의 당일 소수계좌 매수관여 과다종목 |
| 2026-02-09 20:00 | [20260209001620](https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20260209001620&docno=&viewerhost=&viewerport=) | 동일 |
| 2026-02-10 20:00 | [20260210001316](https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20260210001316&docno=&viewerhost=&viewerport=) | 동일 |
| 2026-08-04 20:01 | [20260804000761](https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20260804000761&docno=&viewerhost=&viewerport=) | 특정계좌(군) 매매관여 과다종목 |

`KIND 23 - KRX 시장감시 4 = 발행사·FSS 공시 19`로 정확히 일치한다. 이후 발행사·정기·계약·지분 공시는 OpenDART를 1차 수집원으로, 투자주의·거래정지 등 거래소 시장조치는 KIND를 보완원으로 사용한다. 두 시스템의 접수번호는 체계가 다르므로 날짜·제목·제출인으로 매칭한다.

## 4. 원자료 수집 명세

| 구분 | OpenDART endpoint | 데이터셋 | API 호출 | 정규화 행/파일 | 저장 위치 |
|---|---|---:|---:|---:|---|
| 기업개황 | `/company.json` | 1 | 1 | 1 | `raw/dart/company.json` |
| 공시목록 | `/list.json` | 2 | 3 | 119건 + 19건 | `raw/dart/disclosures_*.json` |
| 전체 재무제표 | `/fnlttSinglAcntAll.json` | 26 | 26 | 3,129행 | `raw/dart/financials/` |
| 주식의 총수 | `/stockTotqySttus.json` | 13 | 13 | 52행 | `raw/dart/share/stock_total_*` |
| 자기주식 | `/tesstkAcqsDspsSttus.json` | 13 | 13 | 234행 | `raw/dart/share/treasury_stock_*` |
| 증자·감자 | `/irdsSttus.json` | 13 | 13 | 215행 | `raw/dart/share/capital_change_*` |
| 최대주주 | `/hyslrSttus.json` | 13 | 13 | 159행 | `raw/dart/share/major_holder_*` |
| 최대주주 변동 | `/hyslrChgSttus.json` | 13 | 13 | 13행 | `raw/dart/share/major_holder_change_*` |
| 공시 원문 | `/document.xml` | 30 | 30 | ZIP 30개·XML 30개 | `raw/dart/documents/` |
| 합계 |  | 124 | 125 | 재무 3,129행·주식 673행 |  |

119건 공시목록은 `page_count=100`이므로 1·2페이지를 호출해 한 파일로 병합했다. 매니페스트의 해당 행에는 `api_call_count=2`, `pages_fetched=[1,2]`, `row_count=119`가 남는다.

공식 명세:

- [공시검색](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)
- [공시서류 원본파일](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003)
- [단일회사 전체 재무제표](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020)
- [주식의 총수 현황](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020002)
- [자기주식·증자·최대주주 API 그룹](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS002)

## 5. 재무 원자료

### 5.1 수집 행렬

분석 주계열은 연결 `CFS`다. 별도 `OFS`는 검산과 별도 사업 분석용으로 보존하고 연결 시계열에 섞지 않는다.

| 기간 | DART 접수번호 | CFS 행 | OFS 행 | 포함 재무제표 |
|---|---:|---:|---:|---|
| 2023 Q1 | [20230515001759](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20230515001759) | 128 | 104 | BS, CF, CIS, SCE |
| 2023 H1 | [20230814000534](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20230814000534) | 131 | 107 | BS, CF, CIS, SCE |
| 2023 Q3 | [20231114000324](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20231114000324) | 133 | 109 | BS, CF, CIS, SCE |
| 2023 FY | [20240318000915](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240318000915) | 162 | 122 | BS, CF, CIS, SCE |
| 2024 Q1 | [20240514001121](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240514001121) | 123 | 100 | BS, CF, CIS, SCE |
| 2024 H1 | [20240814002167](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240814002167) | 127 | 104 | BS, CF, CIS, SCE |
| 2024 Q3 | [20241114001677](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20241114001677) | 133 | 109 | BS, CF, CIS, SCE |
| 2024 FY | [20250317000963](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250317000963) | 143 | 117 | BS, CF, CIS, SCE |
| 2025 Q1 | [20250514000989](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250514000989) | 122 | 100 | BS, CF, CIS, SCE |
| 2025 H1 | [20250814002574](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250814002574) | 128 | 105 | BS, CF, CIS, SCE |
| 2025 Q3 | [20251114001559](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20251114001559) | 129 | 106 | BS, CF, CIS, SCE |
| 2025 FY | [20260316001681](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260316001681) | 145 | 119 | BS, CF, CIS, SCE |
| 2026 Q1 | [20260515001551](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260515001551) | 122 | 101 | BS, CF, CIS, SCE |

### 5.2 연결 핵심 계정

단위는 억원이다. `Q1·H1·Q3`의 매출·영업이익·순이익·OCF는 공시 누계이며, 자산·현금·재고·채권은 각 기간 말 시점 값이다. FY는 연간/기말 값이다. 독립 분기 손익과 현금흐름은 Phase 3에서 누계 차감식으로 계산한다.

| 기간 | 매출 | 영업이익 | 순이익 | 자산 | 현금 | 재고 | 매출채권·기타유동채권 | OCF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 Q1 | 235.713 | 20.334 | 26.748 | 1,703.635 | 102.736 | 367.235 | 37.709 | 131.959 |
| 2023 H1 | 539.268 | 74.360 | 62.417 | 1,663.939 | 302.600 | 280.785 | 50.611 | 196.957 |
| 2023 Q3 | 711.949 | 60.144 | 69.020 | 1,707.718 | 348.785 | 288.834 | 27.935 | 253.095 |
| 2023 FY | 822.963 | 14.647 | 48.861 | 1,659.852 | 295.597 | 239.216 | 42.380 | 211.923 |
| 2024 Q1 | 71.454 | -47.721 | -44.846 | 1,616.736 | 245.609 | 231.640 | 24.127 | -36.900 |
| 2024 H1 | 148.741 | -78.631 | 25.154 | 1,628.929 | 58.324 | 254.501 | 51.502 | -139.750 |
| 2024 Q3 | 187.628 | -146.447 | -27.209 | 1,911.522 | 153.870 | 210.785 | 35.985 | -128.446 |
| 2024 FY | 316.113 | -158.973 | -13.588 | 1,907.839 | 86.660 | 161.571 | 85.010 | -148.797 |
| 2025 Q1 | 19.155 | -57.067 | -15.606 | 1,898.054 | 293.305 | 196.141 | 21.792 | -8.657 |
| 2025 H1 | 94.829 | -85.868 | -32.843 | 1,922.939 | 281.434 | 297.417 | 45.339 | -104.257 |
| 2025 Q3 | 208.943 | -106.199 | -40.448 | 2,069.790 | 248.235 | 429.829 | 57.325 | -174.994 |
| 2025 FY | 660.267 | 0.801 | 89.636 | 2,245.062 | 458.233 | 289.471 | 80.466 | -40.347 |
| 2026 Q1 | 98.055 | -19.659 | 9.348 | 2,253.704 | 333.848 | 374.605 | 38.403 | -52.379 |

핵심 계정 10개 × CFS 13개 기간 = 130개 선택은 전부 `account_id`로 이루어졌고 계정명 fallback은 0건이다. `sj_div`를 함께 사용해 SCE의 반복 계정과 혼동하지 않았다. 값의 원문 문자열과 숫자 변환값을 모두 보존했으며 빈칸과 `-`를 0으로 바꾸지 않았다.

## 6. 계약 원장과 정정 연결

| 출처 ID | 제품 | 계약액(억원) | 계약일 | 계약기간 | 상대방 | 지급조건 | 최신 DART |
|---|---|---:|---|---|---|---|---:|
| `P2025-CORR-01` | CLT INTERFACE BOARD | 88.0588 | 2025-09-29 | 2025-09-22~2026-03-31 | 삼성전자 | 공시상 `-` | [20260102900767](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260102900767) |
| `R03` | CLT 및 SSD Tester | 302.000 | 2026-03-04 | 2026-02-27~2026-12-31 | 삼성전자 | 납품 후 90%, SET UP 후 10% | [20260304901110](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260304901110) |
| `R04`+`R07` | CLT Interface Board | 96.863 | 2026-05-06 | 2026-04-30~2026-09-04 | 삼성전자 | 제품 공급 후 100% | [20260727900650](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260727900650) |
| `R05` | 반도체검사장비(CIB 등) | 120.654 | 2026-06-04 | 2026-05-26~2026-12-31 | 삼성전자 | 제품 공급 후 100% | [20260604900245](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260604900245) |
| `R06` | CLT 및 SSD Tester | 498.500 | 2026-07-10 | 2026-07-07~2026-12-31 | 삼성전자 | 납품 후 90%, SET UP 후 10% | [20260710900182](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260710900182) |

처리 규칙은 다음과 같다.

- 2026-01-02 공시는 2025년 계약의 종료일 정정이므로 2026년 신규계약 합계에서 제외한다.
- `R07`은 `R04`의 종료일을 2026-07-31에서 2026-09-04로 바꾼 정정이며 별도 금액으로 합산하지 않는다.
- 2026년 신규 4건 합계는 `302 + 96.863 + 120.654 + 498.5 = 1,018.017억원`이다.
- 컷오프까지 해지·취소 공시는 0건이다.
- 계약기간 종료일과 지급조건은 매출 인식일·매출 인식률이 아니다. 검수·고객 수락 증거가 없으면 계약별 인식액은 `U`로 둔다.

## 7. 주식·주주·자본 자료

| 데이터셋 | 기간 수 | 원행 | 상태 |
|---|---:|---:|---|
| 증자·감자 | 13 | 215 | 13/13 `000` |
| 최대주주 | 13 | 159 | 13/13 `000` |
| 최대주주 변동 | 13 | 13 | 13/13 `000` |
| 주식의 총수 | 13 | 52 | 13/13 `000` |
| 자기주식 | 13 | 234 | 13/13 `000` |

2026년 1분기 `합계` 행은 다음과 같이 검산된다.

```text
누적 발행 14,355,143 - 누적 감소 1,304,346 = 발행주식 13,050,797
발행주식 13,050,797 - 자기주식 100,000 = 유통주식 12,950,797
```

이 값은 기말 주식 수이며 EPS 계산의 가중평균주식 수와 동일하다고 가정하지 않는다.

## 8. 자동 검산 결과

| 검산 범주 | 개수 | 통과 | 실패 |
|---|---:|---:|---:|
| 원수집 상태 | 1 | 1 | 0 |
| 공시 건수·반기보고서 | 2 | 2 | 0 |
| 재무 페이로드·재무제표 구성 | 26 | 26 | 0 |
| 자산 = 부채 + 자본 | 26 | 26 | 0 |
| BS 현금 = CF 기말현금 | 26 | 26 | 0 |
| 핵심 계정 매핑 | 26 | 26 | 0 |
| 주식·주주 페이로드 | 65 | 65 | 0 |
| 주식 수 등식 | 13 | 13 | 0 |
| 계약 원문 파싱 | 6 | 6 | 0 |
| 계약 고유건수·합계·취소 | 3 | 3 | 0 |
| 합계 | 194 | 194 | 0 |

연결·별도 26개 모두 자산=부채+자본이고 BS 현금과 CF 기말현금이 일치함을 자동 검사로 확인했다. 2023년 비표준 계정 ID와 SCE 반복 계정은 정상 구조이므로 `account_id` 단독 중복제거를 금지하고, 최소 `rcept_no + fs_div + sj_div + account_id + account_nm + account_detail + ord`를 원행 키로 사용한다.

### 수집 중 발견·수정한 오류

1. 수집 스크립트 최초 두 번은 PowerShell 파서 오류로 API 호출 전에 중단됐다. 문자열 보간과 한국어 정규식 구문을 수정했다.
2. 최초 정상 수집은 `total_count=119`를 확인했지만 첫 페이지 100행만 파일에 넣었다. 정규화 검사에서 `100 != 119`로 실패를 탐지했다.
3. 수집기에 자동 페이지 병합을 추가하고 재실행해 1·2페이지 119행을 저장했다. 페이지 수정 직후 검산은 168/168 통과했다.
4. PowerShell에서 UTF-8 옵션 없이 파일을 읽었을 때 한글이 깨져 보였으나, 파일 바이트와 Python UTF-8 JSON 파싱은 정상이었다. 원자료 재수집 대신 이후 검사에 UTF-8을 명시했다.
5. 독립검증으로만 확인했던 BS 현금과 CF 기말현금 일치를 재실행 가능한 검사 26개로 추가했다. 최종 검산은 194/194 통과했다.

## 9. 공통 출처 레지스트리

아래 ID는 계획서, 이후 모델, 차트 하단, 보고서 본문에서 동일하게 사용한다.

| ID | 등급 | 원문 | 사용 범위 |
|---|---|---|---|
| `R01` | A/F | [엑시콘 2026년 1분기보고서](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260515001551) | 제품·재무·재고·채권·OCF·수익인식·주식 수 |
| `R02` | A/F | [엑시콘 2025년 사업보고서](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260316001681) | 2025 실적·사업 구조·과거 비교 |
| `R03` | A/F | [2026-03-04 계약](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260304901110) | 302억원·기간·지급조건 |
| `R04` | A/F | [2026-05-06 계약](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260506900318) | 96.863억원·최초 기간·지급조건 |
| `R05` | A/F | [2026-06-04 계약](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260604900245) | 120.654억원·기간·지급조건 |
| `R06` | A/F | [2026-07-10 계약](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260710900182) | 498.5억원·기간·지급조건 |
| `R07` | A/F | [2026-07-27 정정](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260727900650) | `R04` 종료일 변경 |
| `R08` | C/E | [대신증권 PDF](https://consensus.hankyung.com/analysis/downpdf?report_idx=650132) · [메타데이터](https://markets.hankyung.com/consensus/view/650132) | 7월 계약 전 외부 전망 비교; 실제치 금지 |
| `R09` | A/F | [KRX 정보데이터시스템](https://data.krx.co.kr/) | 가격·시총·상장주식 수; 데이터셋 추출은 가치평가 전 남음 |
| `R10` | A/F | [DART 엑시콘 정기공시 검색](https://dart.fss.or.kr/navi/searchNavi.do?naviCode=A002&naviCrpCik=00611736&naviCrpNm=%EC%97%91%EC%8B%9C%EC%BD%98) | 최신 정기공시·정정 여부 |
| `R11` | C | [SEMI 공식 전망](https://www.semi.org/en/semi-press-release/global-semiconductor-equipment-sales-forecast-to-reach-a-record-229-billion-dollars-in-2028-semi-reports) | 산업 전망; 엑시콘 성장률로 직접 대입 금지 |
| `R12` | A/F·C | [TSMC 2Q26 허브](https://investor.tsmc.com/english/quarterly-results/2026/q2) · [Transcript](https://investor.tsmc.com/english/encrypt/files/encrypt_file/reports/2026-07/547d1696765e05ce3adb81c108ce1c8c1682b80c/TSMC%202Q26%20Transcript.pdf) | 재무 `F`, 경영진 수요 설명 `C` |
| `R13` | A/F·C | [Advantest FY2026 1Q](https://www.advantest.com/en/news/2026/qnpuno0000000cr7-att/E_FR_FY2026_1Q.pdf) | 재무 `F`, AI·HPC 전망 `C` |
| `R14` | A/F | [ISC 2026년 1분기보고서](https://kind.krx.co.kr/external/2026/05/15/000123/20260515000186/11013.htm) | 테스트소켓 구조·공시 실적 비교 |
| `R15` | B/C·A/F | [TechWing IR](https://kind.krx.co.kr/external/dst/irReference/18865/TechWing%20IR%20Book%201Q26.pdf) · [1분기보고서](https://kind.krx.co.kr/external/2026/05/15/001510/20260515003309/11013.htm) | IR 주장은 `C`, 재무는 공시 `F` |
| `R16` | A/F·C | [FormFactor 2Q26](https://investors.formfactor.com/news-releases/news-release-details/formfactor-inc-reports-2026-second-quarter-results) · [10-Q](https://www.sec.gov/Archives/edgar/data/1039399/000103939926000033/form-20260627.htm) | 재무 `F`, HBM 수요 설명 `C` |

## 10. 다음 단계와 남은 제한

- Phase 3에서 CFS 누계 손익·CF를 차감해 독립 분기 시계열을 만든다. Q2=`H1-Q1`, Q3=`Q3-H1`, Q4=`FY-Q3`로 계산하고 연간 합계를 재검산한다.
- 계약 원장의 금액을 매출로 직접 대입하지 않는다. 검수·고객 수락·수익 인식 확인액만 모델 실제치로 전환한다.
- KRX `R09`의 화면명·데이터셋 코드·2026-08-13 다운로드 파일은 가치평가 전에 별도 확보한다.
- 2026년 반기보고서는 2026-08-14 재조회 게이트를 유지한다.
- 일부 외부 원문은 자동 HTTP에서 403이므로 공식 허브와 원문 링크를 병기했으며, 직접 숫자를 사용할 때는 해당 문서의 보존본·페이지 위치를 추가한다.
- XLSX 패키징은 전용 스프레드시트 런타임이 제공되는 세션에서 현재 정규화 JSON을 입력으로 수행한다.
