# 무거운 gradle:8.5-jdk17 이미지 대신 JDK + gradle bin (디스크·다운로드 부담 감소)
FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip \
 && curl -fsSL https://services.gradle.org/distributions/gradle-8.5-bin.zip -o /tmp/gradle.zip \
 && unzip -q /tmp/gradle.zip -d /opt \
 && rm -f /tmp/gradle.zip \
 && ln -s /opt/gradle-8.5/bin/gradle /usr/bin/gradle \
 && rm -rf /var/lib/apt/lists/*

COPY . .
RUN gradle bootJar -x test --no-daemon \
 && rm -rf /root/.gradle/caches /root/.gradle/wrapper

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY --from=build /app/build/libs/backend-spring-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
