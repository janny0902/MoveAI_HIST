package com.moveai.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "moveai")
public class AppProperties {
    private String aiBaseUrl = "http://backend-ai:8000";
    private String kakaoRestKey = "";
    private String cargoPhotoDir = "/data/cargo-photos";

    public String getAiBaseUrl() {
        return aiBaseUrl;
    }

    public void setAiBaseUrl(String aiBaseUrl) {
        this.aiBaseUrl = aiBaseUrl;
    }

    public String getKakaoRestKey() {
        return kakaoRestKey;
    }

    public void setKakaoRestKey(String kakaoRestKey) {
        this.kakaoRestKey = kakaoRestKey;
    }

    public String getCargoPhotoDir() {
        return cargoPhotoDir;
    }

    public void setCargoPhotoDir(String cargoPhotoDir) {
        this.cargoPhotoDir = cargoPhotoDir;
    }
}
