package com.moveai.backend.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "trucks")
public class Truck {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String driverName;
    private String phone;
    private String truckNumber;
    private Double capacityTons = 11.0;
    private Double capacityM3 = 50.0;
    private String vehicleType;
    private Boolean profileCompleted = false;
    private String originCode;
    private String originName;
    private String destinationCode;
    private String destinationName;
    private Double currentLocationLat;
    private Double currentLocationLng;
    private String status = "IDLE";
    private Double remainingVolumePercent = 100.0;
    private Double expectedAddedFillPercent;
    private Double baselineOccupiedPercent;
    private Long activeRequestId;
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();

    @PreUpdate
    void touch() {
        updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getDriverName() { return driverName; }
    public void setDriverName(String driverName) { this.driverName = driverName; }
    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }
    public String getTruckNumber() { return truckNumber; }
    public void setTruckNumber(String truckNumber) { this.truckNumber = truckNumber; }
    public Double getCapacityTons() { return capacityTons; }
    public void setCapacityTons(Double capacityTons) { this.capacityTons = capacityTons; }
    public Double getCapacityM3() { return capacityM3; }
    public void setCapacityM3(Double capacityM3) { this.capacityM3 = capacityM3; }
    public String getVehicleType() { return vehicleType; }
    public void setVehicleType(String vehicleType) { this.vehicleType = vehicleType; }
    public Boolean getProfileCompleted() { return profileCompleted; }
    public void setProfileCompleted(Boolean profileCompleted) { this.profileCompleted = profileCompleted; }
    public String getOriginCode() { return originCode; }
    public void setOriginCode(String originCode) { this.originCode = originCode; }
    public String getOriginName() { return originName; }
    public void setOriginName(String originName) { this.originName = originName; }
    public String getDestinationCode() { return destinationCode; }
    public void setDestinationCode(String destinationCode) { this.destinationCode = destinationCode; }
    public String getDestinationName() { return destinationName; }
    public void setDestinationName(String destinationName) { this.destinationName = destinationName; }
    public Double getCurrentLocationLat() { return currentLocationLat; }
    public void setCurrentLocationLat(Double currentLocationLat) { this.currentLocationLat = currentLocationLat; }
    public Double getCurrentLocationLng() { return currentLocationLng; }
    public void setCurrentLocationLng(Double currentLocationLng) { this.currentLocationLng = currentLocationLng; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Double getRemainingVolumePercent() { return remainingVolumePercent; }
    public void setRemainingVolumePercent(Double remainingVolumePercent) { this.remainingVolumePercent = remainingVolumePercent; }
    public Double getExpectedAddedFillPercent() { return expectedAddedFillPercent; }
    public void setExpectedAddedFillPercent(Double expectedAddedFillPercent) { this.expectedAddedFillPercent = expectedAddedFillPercent; }
    public Double getBaselineOccupiedPercent() { return baselineOccupiedPercent; }
    public void setBaselineOccupiedPercent(Double baselineOccupiedPercent) { this.baselineOccupiedPercent = baselineOccupiedPercent; }
    public Long getActiveRequestId() { return activeRequestId; }
    public void setActiveRequestId(Long activeRequestId) { this.activeRequestId = activeRequestId; }
}
