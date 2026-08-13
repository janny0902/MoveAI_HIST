package com.moveai.backend.config;

import com.moveai.backend.service.TerminalRegistryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * 기동 직후 터미널 캐시를 시드로 채운 뒤 matching을 비동기 갱신.
 * 재시작 직후 빈 드롭다운을 막는다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TerminalWarmupRunner implements ApplicationRunner {

    private final TerminalRegistryService terminalRegistry;

    @Override
    public void run(ApplicationArguments args) {
        try {
            int n = terminalRegistry.warmOnStartup();
            log.info("terminal cache warmed: {} entries", n);
            terminalRegistry.refreshAsync();
        } catch (Exception e) {
            log.warn("terminal warmup failed: {}", e.toString());
        }
    }
}
