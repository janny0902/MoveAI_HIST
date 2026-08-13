package com.moveai.backend.controller;

import com.moveai.backend.service.DriverService;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/drivers")
public class DriverController {
    private final DriverService driverService;

    public DriverController(DriverService driverService) {
        this.driverService = driverService;
    }

    @PostMapping("/login")
    public Map<String, Object> login(@RequestBody Map<String, Object> body) {
        String phone = String.valueOf(body.getOrDefault("phone", ""));
        String truckNumber = String.valueOf(body.getOrDefault("truckNumber", ""));
        String driverName = body.get("driverName") == null ? null : String.valueOf(body.get("driverName"));
        return driverService.login(phone, truckNumber, driverName);
    }

    @GetMapping("/{id}")
    public Map<String, Object> get(@PathVariable Long id) {
        return driverService.get(id);
    }

    @GetMapping({"", "/"})
    public Map<String, Object> list() {
        return driverService.list();
    }

    @PostMapping("/{id}/profile")
    public Map<String, Object> profile(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        return driverService.updateProfile(id, body);
    }

    @PostMapping("/{id}/route")
    public Map<String, Object> route(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        String origin = String.valueOf(body.getOrDefault("originCode", ""));
        String dest = String.valueOf(body.getOrDefault("destinationCode", ""));
        return driverService.updateRoute(id, origin, dest);
    }
}
