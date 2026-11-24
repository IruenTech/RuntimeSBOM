# 운영 적용 가이드 (검증 전용)

## 필수 준비

- 서버 JVM 버전의 `java -version` 확인. Java 8 이상을 목표로 빌드하되 AIX/OpenJ9 실측은 별도 검증.
- 격리된 검증 환경에서 `sh scripts/verify-official-asm.sh`로 **공식 ASM 포함 JAR** 검증.
- `tracePackages`는 최소한으로 지정하고 초기에는 `interval=0` 및 `collectorUrl` 없이 로컬 출력부터 확인.
- 권한 최소화, 저장 경로 디스크 용량 제한, 비밀 토큰 환경변수 사용, TLS(실서버) 적용.

## Tomcat 또는 JEUS/WebLogic

WAS JVM 시작 옵션에 추가 (셸 인용은 실제 서버 문법에 맞춰 조정):

```text
-javaagent:/opt/runtime-sbom/runtime-sbom-agent-0.8.0.jar=output=/var/log/runtime-sbom/sbom.json,interval=60,tracePackages=org.apache.commons;com.fasterxml.jackson,maxTransformErrors=50,maxTransformedClasses=2000
```

부모/자식 클래스 로더가 Agent Recorder를 참조할 수 없다면 메서드 계측을 건너뜁니다. JAR 목록 수집과 메서드 실행 추적은 별도 결과이며, 일부 계측 불가 라이브러리는 로딩 기록만 남습니다.

## Spring Boot

```sh
java '-javaagent:/opt/runtime-sbom/runtime-sbom-agent-0.8.0.jar=output=runtime-sbom.json,interval=60,tracePackages=org.apache.commons' -jar application.jar
```

Boot 2와 Boot 3는 서로 다른 중첩 JAR URL을 사용하므로 각 버전의 실제 WAR/JAR 빌드로 식별 정확성을 따로 점검합니다.

## 중지/장애 복구

`killSwitchFile=/run/runtime-sbom.disable` 옵션을 지정한 뒤 해당 파일을 만들어 추적 기록을 중단할 수 있습니다. 현재 구현은 설정 파일을 스냅샷 저장 시 재확인하므로 즉시 중지 스위치가 아니며 이미 변환된 바이트코드는 돌아오지 않습니다. 완전 비활성화는 JVM을 에이전트 없이 재시작해야 합니다.

## Windows

PowerShell에서 명령 전체 문자열을 적절히 인용하고 `JAVA_TOOL_OPTIONS` 또는 WAS 서비스 JVM 옵션에 등록합니다. Linux용 `/var/log`나 `/run` 경로를 그대로 사용하지 않습니다.
