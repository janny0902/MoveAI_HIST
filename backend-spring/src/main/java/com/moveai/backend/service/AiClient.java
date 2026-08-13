package com.moveai.backend.service;

import com.moveai.backend.config.AppProperties;
import java.util.Map;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

@Component
public class AiClient {
    private final AppProperties props;
    private final RestTemplate restTemplate;

    public AiClient(AppProperties props) {
        this.props = props;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);
        factory.setReadTimeout(180_000);
        this.restTemplate = new RestTemplate(factory);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> analyzeImage(byte[] bytes, String filename) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return filename == null ? "upload.jpg" : filename;
            }
        };
        body.add("file", resource);
        HttpEntity<MultiValueMap<String, Object>> entity = new HttpEntity<>(body, headers);
        String url = props.getAiBaseUrl() + "/ai/analyze-image";
        return restTemplate.postForObject(url, entity, Map.class);
    }
}
