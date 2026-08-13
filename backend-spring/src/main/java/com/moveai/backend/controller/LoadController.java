package com.moveai.backend.controller;

import com.moveai.backend.service.LoadService;
import java.util.Map;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/load")
public class LoadController {
    private final LoadService loadService;

    public LoadController(LoadService loadService) {
        this.loadService = loadService;
    }

    @PostMapping("/upload")
    public Map<String, Object> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "truckId", defaultValue = "1") Long truckId) {
        return loadService.upload(file, truckId);
    }
}
