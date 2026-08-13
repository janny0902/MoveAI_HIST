FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /workspace
COPY . .
RUN apt-get update && apt-get install -y --no-install-recommends unzip curl \
    && rm -rf /var/lib/apt/lists/*
# Use Gradle wrapper if present; otherwise install gradle
RUN if [ -f ./gradlew ]; then \
      chmod +x ./gradlew && ./gradlew bootJar --no-daemon; \
    else \
      curl -fsSL https://services.gradle.org/distributions/gradle-8.10.2-bin.zip -o /tmp/gradle.zip \
      && unzip -q /tmp/gradle.zip -d /opt \
      && /opt/gradle-8.10.2/bin/gradle bootJar --no-daemon; \
    fi

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY --from=build /workspace/build/libs/*.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
