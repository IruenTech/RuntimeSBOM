# Phase29 — 장시간 성능 추세 및 WAS 수명주기 검증 (운영 배포 승인 HOLD)

## 목적과 범위

- 기존 **공식 ASM 9.7.1 Shaded Agent v1.0.0-rc16**을 재빌드하지 않고 재사용합니다.
- 바이트 동일성: SHA-256 `ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a`.
- 모든 자동 테스트는 **loopback/임시 스테이징 환경**만 사용합니다.
- *PASS*는 해당 시험 시나리오 성공을 뜻합니다. 운영 적용 승인이나 메모리 누수 부재 증명이 아닙니다.

## 신규 시험 1 — 창별 지속 부하 관측

```bash
python3 scripts/phase29-sustained.py --warmup 10 --window-seconds 60 --windows 5 --concurrency 8
```

모드별로 **하나의 JVM**을 유지하며 5개 연속 창을 기록합니다. 모드: Agent 없음 / 클래스 로딩만 / ASM 메서드 실행 추적.
각 창의 TPS, P95, P99, HTTP 오류, Linux 프로세스 RSS/CPU, `jstat -gc`에서 읽을 수 있는 GC 차이를 JSON으로 기록합니다. 지원하지 않는 메트릭은 `null`이며 임의의 0으로 채우지 않습니다.

- 결과: `results/phase29/sustained.json` 및 `results/phase29/sustained/{mode}/window-*.json`
- **1시간 이상 합성 시험 예시:** `--window-seconds 300 --windows 12` (3모드 각각 60분, 합계 3시간 이상 소요)
- RSS 시작·끝 차이는 **리뷰 신호**이지 GC로 회수 가능한 객체, 클래스 로더 누수나 Java heap 누수 여부를 입증하지 않습니다. 적절한 운영 판단을 위해 JFR, heap dump, 클래스 로더 통계가 필요합니다.
- 실제 WAS의 업무 트래픽과 다른 합성 HTTP 작업이므로 측정치를 운영 SLO 승인에 사용하지 않습니다.

## 신규 시험 2 — Collector 장애 / JVM 재시작 / 중복 수신

```bash
python3 scripts/phase29-outage-replay.py --offline-jvms 3 --outage-seconds 30
```

1. Collector 미기동 상태에서 서로 다른 JVM 3개가 SBOM 생성·종료 → 로컬 영속 큐 3개 확인
2. Collector 복구 상태에서 네 번째 JVM 기동 → 대기열 3개 + 신규 1개가 별도 자산으로 저장
3. Collector 종료·재시작 (같은 데이터베이스) → 동일 배송 ID와 같은 페이로드 재전송
4. 중복 스냅샷 없이 원래 기록만 유지하고 로컬 큐가 비어 있는지 검증

시험 자체의 대기 시간은 주어진 `--outage-seconds`로 한정되며, 수시간 동안 디스크가 가득 차거나 권한이 변하는 경우는 보장하지 않습니다. 각 JVM은 큐를 *순차적으로* 사용하며 동시 공유하지 않습니다.

## 신규 시험 3 — 실제 Spring Boot / Tomcat 스테이징 수명주기

공식 JAR을 **동일 SHA-256**으로 가져오고 Maven 빌드가 가능한 격리된 스테이징 환경에서만 실행합니다.

```bash
python3 scripts/phase29-was-lifecycle.py --app spring-boot2 --requests 40
python3 scripts/phase29-was-lifecycle.py --app spring-boot3 --requests 40
python3 scripts/phase29-was-lifecycle.py --app tomcat9  --tomcat-home /tmp/isolated-tomcat9 --requests 40
python3 scripts/phase29-was-lifecycle.py --app tomcat10 --tomcat-home /tmp/isolated-tomcat10 --requests 40
```

- Boot: 독립 JVM 두 번 재시작; 두 경우 `commons-lang3`의 실제 HTTP 호출과 `METHOD_EXECUTED`/PURL/해시 검증
- Tomcat: **별도 CATALINA_BASE**를 생성해 그 안의 테스트 WAR만 삭제 후 재배포; JVM은 유지하고 새 클래스 로더가 증거에 반영되는지 확인
- WAR 재배포 후 새 클래스 로더 ID가 확인되더라도 **이전 로더의 GC/회수**는 입증되지 않습니다. JFR/heap dump 별도 분석이 필요합니다.
- 잘못된 경로·기동 실패·메타데이터 누락은 `FAIL`로 처리하며 `results/phase29/live/<app>/`에 로그와 JSON을 남깁니다.
- 이 환경에는 Maven과 Tomcat 배포판이 없어 **이 실서버 시험을 실행하지 못했습니다**. GitHub Actions에서 별도 재현해야 합니다.

## GitHub Actions

워크플로: `Phase29 official rc16 WAS lifecycle and outage rehearsal (manual, never deploy)`.

`phase26_run_id`에는 성공한 Phase26 GitHub Actions Run ID를 넣으세요. `run_live_was=yes`로 Boot2/3, Tomcat9/10 실서버 수명주기를 실행할 수 있습니다. Tomcat은 승인된 아카이브 버전을 SHA-512 검증 후 임시 설치합니다. `run_extended=yes`는 합성 창별 측정을 확장할 뿐, 실제 WAS 장시간 부하 시험을 뜻하지 않습니다.

최종 `human-review-gate` 작업은 로컬 4개 그룹과 4종 실제 WAS 수명주기 검증이 모두 제출된 경우에만 `ELIGIBLE_FOR_HUMAN_REVIEW`로 표시하며 운영 배포는 `HOLD`를 유지합니다. 실제 내부 JAR 바이트의 SHA-256도 SBOM의 SHA와 독립적으로 비교합니다.

실패한 단계에서 관련 출력은 `phase29-real-was-<app>` 또는 `phase29-official-local-rehearsal` 아티팩트에 보존됩니다. 실패를 `HOLD` 판정에서 누락시키지 마세요.

## 운영 승인에 추가로 필요한 시험

- 실제 운영 유사 데이터/부하의 피크·주간·배치 작업에서 baseline/loaded-only/ASM 비교
- 1~24시간 이상 CPU, heap after GC, RSS, JFR, p95/p99, 오류율을 관찰하고 SLO 기준 담당자 승인
- Tomcat undeploy + Full GC 후 오래된 ClassLoader 회수 확인 (JFR, `jcmd VM.classloader_stats`, heap dump)
- Collector 디스크 용량 고갈, 전송 큐 권한 오류, 503/429, 연결 끊김, 다중 프로세스 큐 독점 확인
- JEUS/WebLogic, AIX + 해당 JVM 공급사의 Instrumentation 지원성·보안 정책·부하 검증
- 독립 검토자의 배포 승인/롤백 절차. **productionDeployment=HOLD** 유지.
