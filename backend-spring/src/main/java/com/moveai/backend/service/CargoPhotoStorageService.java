package com.moveai.backend.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class CargoPhotoStorageService {
    private final Path root;

    public CargoPhotoStorageService(
            @Value("${moveai.cargo-photo-dir:/data/cargo-photos}") String dir
    ) throws IOException {
        this.root = Path.of(dir).toAbsolutePath().normalize();
        Files.createDirectories(this.root);
    }

    public String store(MultipartFile file) throws IOException {
        String original = file.getOriginalFilename() == null ? "photo.jpg" : file.getOriginalFilename();
        String ext = "";
        int dot = original.lastIndexOf('.');
        if (dot >= 0) ext = original.substring(dot);
        String name = UUID.randomUUID().toString().replace("-", "") + ext;
        Path target = root.resolve(name);
        Files.write(target, file.getBytes());
        return "/uploads/cargo-photos/" + name;
    }
}
