package com.moveai.backend.controller;

import com.moveai.backend.config.AppProperties;
import com.moveai.backend.service.CargoPhotoStorageService;
import com.moveai.backend.service.LoadService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/load")
public class LoadController {
    private final LoadService loadService;
    private final CargoPhotoStorageService cargoPhotoStorage;
    private final AppProperties props;
    private final RestTemplate restTemplate;

    public LoadController(
            LoadService loadService,
            CargoPhotoStorageService cargoPhotoStorage,
            AppProperties props,
            RestTemplate restTemplate) {
        this.loadService = loadService;
        this.cargoPhotoStorage = cargoPhotoStorage;
        this.props = props;
        this.restTemplate = restTemplate;
    }

    @PostMapping("/upload")
    public Map<String, Object> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "truckId", defaultValue = "1") Long truckId) {
        return loadService.upload(file, truckId);
    }

    @PostMapping("/analyze-floor")
    public Map<String, Object> analyzeFloor(@RequestParam("file") MultipartFile file) throws Exception {
        String photoUrl = cargoPhotoStorage.store(file);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        ByteArrayResource resource = new ByteArrayResource(file.getBytes()) {
            @Override
            public String getFilename() {
                return file.getOriginalFilename() == null ? "floor.jpg" : file.getOriginalFilename();
            }
        };
        body.add("file", resource);
        ResponseEntity<Map> aiRes = restTemplate.exchange(
                props.getAiBaseUrl() + "/ai/analyze-floor-cargo",
                HttpMethod.POST,
                new HttpEntity<>(body, headers),
                Map.class
        );
        Map analysis = aiRes.getBody() != null ? aiRes.getBody() : Map.of();
        Map<String, Object> result = new LinkedHashMap<>(analysis);
        result.putIfAbsent("filename", file.getOriginalFilename());
        result.put("photoUrl", photoUrl);
        return result;
    }

    @PostMapping("/cargo-photo")
    public Map<String, Object> uploadCargoPhoto(@RequestParam("file") MultipartFile file) throws Exception {
        String photoUrl = cargoPhotoStorage.store(file);
        return Map.of(
                "photoUrl", photoUrl,
                "filename", file.getOriginalFilename() == null ? "" : file.getOriginalFilename()
        );
    }
}
