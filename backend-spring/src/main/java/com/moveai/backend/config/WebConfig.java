package com.moveai.backend.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.nio.file.Path;
import java.time.Duration;

@Configuration
public class WebConfig {

    @Value("${moveai.cargo-photo-dir:/data/cargo-photos}")
    private String cargoPhotoDir;

    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        // Depth/YOLO 첫 추론은 수분 소요 가능
        return builder
                .setConnectTimeout(Duration.ofSeconds(15))
                .setReadTimeout(Duration.ofMinutes(3))
                .build();
    }

    /** 관리자 BFF → Cloud Run (매칭 후보 많을 때 수 분 소요 가능) */
    @Bean(name = "adminProxyRestTemplate")
    public RestTemplate adminProxyRestTemplate(RestTemplateBuilder builder) {
        return builder
                .setConnectTimeout(Duration.ofSeconds(30))
                .setReadTimeout(Duration.ofMinutes(15))
                .build();
    }

    @Bean
    public WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                        .allowedOrigins("*")
                        .allowedMethods("*");
                registry.addMapping("/uploads/**")
                        .allowedOrigins("*")
                        .allowedMethods("GET", "HEAD", "OPTIONS");
            }

            @Override
            public void addResourceHandlers(ResourceHandlerRegistry registry) {
                String loc = Path.of(cargoPhotoDir).toAbsolutePath().normalize().toUri().toString();
                if (!loc.endsWith("/")) loc = loc + "/";
                registry.addResourceHandler("/uploads/cargo-photos/**")
                        .addResourceLocations(loc);
            }
        };
    }
}
