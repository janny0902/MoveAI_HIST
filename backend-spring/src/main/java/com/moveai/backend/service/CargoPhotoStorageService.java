package com.moveai.backend.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Locale;
import java.util.UUID;

/** 화물 등록 사진 로컬 저장 → /uploads/cargo-photos/... */
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
        String original = file.getOriginalFilename() != null ? file.getOriginalFilename() : "cargo.jpg";
        String ext = ".jpg";
        int dot = original.lastIndexOf('.');
        if (dot >= 0) {
            String e = original.substring(dot).toLowerCase(Locale.ROOT);
            if (e.matches("\\.(jpe?g|png|webp|gif)")) ext = e;
        }
        String name = System.currentTimeMillis() + "-" + UUID.randomUUID().toString().substring(0, 8) + ext;
        Path target = root.resolve(name);
        Files.copy(file.getInputStream(), target, StandardCopyOption.REPLACE_EXISTING);
        return "/uploads/cargo-photos/" + name;
    }

    public Path root() {
        return root;
    }
}
