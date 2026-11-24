# Phase21: HTTP provenance, embedded dependency identity and staging gates

## 1. 범위

Phase21은 추가 기능을 무조건 확장하는 대신, **배포된 라이브러리와 JVM 실행 증거 사이의 동일성**을 검증하도록 설계했습니다. 하나의 Maven PURL이 물리적으로 서로 다른 JAR(해시 상이)로 두 번 배포되는 경우에도 JAR·로더별 실행을 분리해야 합니다.

계측 범위와 상태는 다음과 같습니다:

- **`CLASS_LOADED`:** 실제 JVM 로딩을 관측. 어떤 메서드가 호출되었는지 알 수 없거나 호출을 관측하지 못함
- **`METHOD_EXECUTED`:** 해당 파일·로더에서 변환된 클래스의 메서드 진입이 1회 이상 관측
- **격리 로더:** `Recorder`에 접근할 수 없을 경우 원본 바이트코드를 유지하며 메서드 실행 여부를 추정하지 않음
- **지표:** 관측 메서드 진입 횟수는 추적 이벤트이며 비즈니스 거래 건수 또는 취약점 악용 가능성을 나타내지 않음

## 2. 신규 HTTP fixture 시험

테스트 자산:

| 구성요소 | 코드·동작 | 기대값(HTTP 80회) |
|---|---|---|
| old JAR | `Helper.compute(i) = i*3+1` | 호출 80, `METHOD_EXECUTED` |
| new JAR | `Helper.compute(i) = i*5+2` | 호출 160, `METHOD_EXECUTED` |
| isolated new JAR | 부모가 없는 클래스 로더, 동일 new JAR | 실제 호출 80, 관측 0, `CLASS_LOADED` |

각 HTTP 요청은 old 1회, new 2회, isolated new 1회를 실제 호출하고 `checksum=25`를 반환합니다. 외부의 테스트 클라이언트가 80개 요청을 병렬로 실행하며 성공 응답과 `/stats` 값을 검증합니다. 독립 정답은 **HTTP 성공 횟수와 원본 JAR 해시**로 생성합니다. 이 JAR의 Maven 좌표는 `pkg:maven/com.example.fixture/fixture-core@1.2.3`로 동일하지만 해시가 다릅니다.

통제된 fixture의 Precision/Recall은 실제 설치 환경 전체의 오픈소스 탐지율로 해석하지 않습니다. 짧은 HTTP TPS 및 P95/P99는 인수성능 기준이 아닙니다.

## 3. 실제 Spring Boot·Tomcat 검증

프로젝트 내 실서버 실행기는 각각 다음 조건을 시험합니다.

1. Agent 없는 baseline
2. Agent의 클래스 로딩만 관측(메서드 실행 증거 0이어야 함)
3. 공식 ASM 계측으로 `org.apache.commons.lang3` 메서드 호출 탐지

`phase21-staging-live.py`는 세 조건의 실서버 HTTP 시험을 실행한 뒤 다음을 **추가 검증**합니다.

- Spring Boot `BOOT-INF/lib/commons-lang3-3.14.0.jar` 또는 WAR `WEB-INF/lib/...`에서 SHA-256을 직접 계산
- SBOM `pkg:maven/org.apache.commons/commons-lang3@3.14.0` 구성요소의 해시 일치 여부
- 출처 문자열에 물리적 라이브러리 파일명이 포함되는지 여부
- 클래스 로더 식별자의 존재와 실행 모드별 `METHOD_EXECUTED`/`CLASS_LOADED` 상태 일치
- SBOM의 같은 Maven PURL이 다른 JAR 해시로 잘못 귀속되거나 중복 식별되지 않았는지 여부
- 사용한 공식 Agent SHA-256이 실서버 결과에 기록된 값과 동일한지 여부

**현재 환경에서는 이 실제 WAS 절차를 수행하지 못했습니다.** `HOLD`가 정상이고 임의로 PASS 상태를 생성하지 않습니다.

## 4. CI와 승인 게이트

`.github/workflows/phase21-integration.yml`은 다음을 정의합니다.

- JDK 21 로컬 다중 로더 fixture 테스트(테스트 전용 내부 ASM)
- 공식 ASM 9.7.1 Shaded JAR Maven 패키징 및 검사
- 동일 공식 JAR에 대한 JDK 8·11·17·21 실행 검증
- 공식 JAR을 활용한 Spring Boot 2·3 실서버 HTTP 시험

Tomcat 9·10.1의 실제 배포판은 별도의 승인된 테스트 호스트를 사용해야 합니다. JEUS·WebLogic·AIX는 제조사 및 플랫폼 JVM 조건에서 별도로 검증해야 합니다.

`phase21-release-gate.py`는 공식 JAR 감사, 4개 JDK, Spring Boot 2·3, Tomcat 9·10.1 및 로컬 fixture 결과를 모두 요구합니다. 하나라도 누락되면 `HOLD`이며 전부 통과해도 **운영 출시 자동 승인 대신 수동 스테이징 검토 대상**으로만 판정합니다.

검증 JSON은 서명된 출처 증명이 아닙니다. CI 실행 로그와 바이너리 해시를 별도로 보관하고 검토해야 합니다.

## 5. 성능 승인 (추후 실환경 검증 필요)

동일 하드웨어에서 Agent 미적용, 로딩 전용, ASM 계측을 비교하여 워밍업 후 TPS, P50/P95/P99, CPU, RSS/Heap, GC, 실패율을 수집합니다. 반복 실행과 신뢰구간 또는 충분한 반복 통계 분석 없이 성능 저하율을 확정하지 않습니다. 현 예제 테스트의 반복 수와 시간은 회귀 진단용이며 사전 정의된 운영 SLO 충족을 보장하지 않습니다.

## 6. 보안·운영 제한

- 운영 환경은 재현되지 않았고 Agent를 업무 트래픽에 붙인 결과가 없습니다.
- `-javaagent` 설정은 JVM 프로세스 시작 옵션을 바꾸므로 WAS 관리자 승인 후 비운영 환경에서 먼저 시험해야 합니다.
- 운영 로그/수집 큐에는 응용 클래스·메서드명 및 컴포넌트 경로 등 민감할 수 있는 자산 메타데이터가 포함될 수 있으므로 접근 통제 및 보존 기간을 설정하십시오.
- 로컬 테스트 전용 ASM은 재배포하지 마십시오. 실제 고객 환경에는 공식 의존성이 재배치된 검증된 JAR만 사용하십시오.
- 동일 PURL·다른 해시가 항상 악성이라는 의미는 아닙니다. 재패키징이나 수정 빌드 등 원인을 조사해야 합니다.
