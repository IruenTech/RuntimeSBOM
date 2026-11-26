# RuntimeSBOM Agent 28단계: 운영 유사 검증 실행 지침

## 검증 범위

이 단계는 업로드된 **공식 rc16 ASM 9.7.1 Shaded Agent (SHA-256 ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a)** 를 사용합니다. 재빌드한 JAR이 아니라 같은 검증용 바이너리를 사용합니다. Java 21 Linux, Java 내장 HTTP 서버와 Python 참조 Collector를 사용하며, 실제 Tomcat, Spring Boot, JEUS, WebLogic 또는 AIX 실환경 시험이 아닙니다.

### 1. 성능 비교

- `python3 scripts/phase28-performance.py --warmup 10 --duration 60 --repeats 3 --concurrency 8`
- 3조건: Agent 없음 / 클래스 로딩 전용 / ASM 메서드 계측
- 모드별 개별 JVM으로 비교, 라운드마다 실행 순서 교차, HTTP 성공률, TPS, P95/P99 수집
- Linux에서 프로세스 CPU 소요 시간, 관측된 RSS, jstat GC 발생 수/시간(도구가 있을 때) 수집
- 모든 원시 실행: `results/phase28/run-*/`, 요약: `results/phase28/performance.json`
- 데이터는 합성 로컬 요청이며, TPS가 높게 나오더라도 실제 운영 성능 우수의 근거가 아님
- **실제 운영용 기준**: 환경별 별도 SLO 합의, 충분한 워밍업, 최소 3회 재현, 정상적인 오류율, 대상 CPU·Memory·GC 자원 예산; SLA 미충족시 롤백

### 2. 전송 장애 복구

- `python3 scripts/phase28-resilience.py`
- Collector가 다운된 상태의 정상 JVM 종료 시 디스크 영속 큐 보존
- Collector 복구 후 **새 JVM 프로세스**로 재시작 → 이전 스냅샷을 먼저 재전송 → 새 스냅샷 저장
- 동일 delivery ID의 동일 페이로드 재전송 → 스냅샷 수 중복 증가 없음
- 확인 위치: `results/phase28/resilience.json`
- 테스트 큐는 단일 JVM 소유입니다. 여러 JVM에서 같은 `queueDir`을 사용하지 마세요.
- 현재 큐가 FULL인 경우 새 스냅샷을 거부하므로, 파일 시스템의 가용 공간과 큐 임계치 경고가 별도로 필요합니다.

### 3. 실제 WAS/환경별 현장 실행 체크리스트 (이 패키지에서 실행되지 않음)

1. 운영과 분리된 스테이징 WAS 준비: 동일 JDK, WAR/JAR, 공유 라이브러리, 설정과 유사 부하
2. Agent 없는 상태로 실제 endpoint 10분 워밍업 및 30분 이상 측정, TPS·P95/P99·CPU·RSS·GC 기록
3. 동일 WAS에서 로딩 전용, 제한된 `tracePackages` ASM 계측을 각각 **동일 부하**로 반복 검증
4. 정확한 PURL 및 SHA-256, 서로 다른 로더의 중복 인스턴스, METHOD_EXECUTED가 관측 한계를 정확하게 표기하는지 확인
5. **Tomcat**: WAR 재배포·undeploy·redeploy 후 클래스 로더 식별자 변경, 오래된 로더 참조가 남아 있는지 확인; Heap dump 또는 JFR로 로더 회수 관찰
6. **Spring Boot**: 애플리케이션 재시작, Boot 2/3 중첩 JAR, 실제 내부 라이브러리 해시 검사
7. **Collector**: 503/429/Timeout, WAN 지연, 중복 요청, 용량 초과/디스크 Full; 최소 24시간 수집 및 장애 주입
8. **상용 WAS/AIX**: 라이선스/승인 범위, IBM Semeru/OpenJ9 등 JVM별 API, 클래스로더 접근성, 보안 매니저, AIX 성능 명령을 별도로 확인
9. 운영 승인 담당자가 **배포·롤백 절차, 증거 서명/보관, 수집된 민감정보 및 로그 정책** 검토

### 4. 보수적 판정

- `phase28-local-gate.py`의 PASS는 정해진 테스트를 실행했다는 의미입니다.
- **실제 WAS 성능 SLO 검증, 24시간 지속 부하, JEUS/WebLogic/AIX 시험은 포함되지 않습니다.**
- 성능 수치에 자체적으로 운영 승인 임계치를 적용하지 않습니다.
- 모든 리포트의 `productionDeployment`는 `HOLD` 입니다.
