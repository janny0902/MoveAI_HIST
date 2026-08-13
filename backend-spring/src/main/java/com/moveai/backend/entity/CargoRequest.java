package com.moveai.backend.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "cargo_requests")
public class CargoRequest {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String origin;
    private String destination;
    private String via;
    private String originCode;
    private String destinationCode;
    private String viaCodes;
    private Integer boxCount = 0;
    private Double totalVolumeM3 = 0.0;
    private Double totalWeightKg = 0.0;
    private Integer proposedFee = 0;
    private Double expectedFillPercent = 0.0;
    private Long assignedTruckId;
    private String status = "PENDING";
    @Column(columnDefinition = "TEXT")
    private String briefing;
    private Double extraDistanceKm;
    private Integer extraFuelCost;
    private Integer netProfit;
    private Double esgReductionKg;
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();

    @PreUpdate
    void touch() {
        updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getOrigin() { return origin; }
    public void setOrigin(String origin) { this.origin = origin; }
    public String getDestination() { return destination; }
    public void setDestination(String destination) { this.destination = destination; }
    public String getVia() { return via; }
    public void setVia(String via) { this.via = via; }
    public String getOriginCode() { return originCode; }
    public void setOriginCode(String originCode) { this.originCode = originCode; }
    public String getDestinationCode() { return destinationCode; }
    public void setDestinationCode(String destinationCode) { this.destinationCode = destinationCode; }
    public String getViaCodes() { return viaCodes; }
    public void setViaCodes(String viaCodes) { this.viaCodes = viaCodes; }
    public Integer getBoxCount() { return boxCount; }
    public void setBoxCount(Integer boxCount) { this.boxCount = boxCount; }
    public Double getTotalVolumeM3() { return totalVolumeM3; }
    public void setTotalVolumeM3(Double totalVolumeM3) { this.totalVolumeM3 = totalVolumeM3; }
    public Double getTotalWeightKg() { return totalWeightKg; }
    public void setTotalWeightKg(Double totalWeightKg) { this.totalWeightKg = totalWeightKg; }
    public Integer getProposedFee() { return proposedFee; }
    public void setProposedFee(Integer proposedFee) { this.proposedFee = proposedFee; }
    public Double getExpectedFillPercent() { return expectedFillPercent; }
    public void setExpectedFillPercent(Double expectedFillPercent) { this.expectedFillPercent = expectedFillPercent; }
    public Long getAssignedTruckId() { return assignedTruckId; }
    public void setAssignedTruckId(Long assignedTruckId) { this.assignedTruckId = assignedTruckId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getBriefing() { return briefing; }
    public void setBriefing(String briefing) { this.briefing = briefing; }
    public Double getExtraDistanceKm() { return extraDistanceKm; }
    public void setExtraDistanceKm(Double extraDistanceKm) { this.extraDistanceKm = extraDistanceKm; }
    public Integer getExtraFuelCost() { return extraFuelCost; }
    public void setExtraFuelCost(Integer extraFuelCost) { this.extraFuelCost = extraFuelCost; }
    public Integer getNetProfit() { return netProfit; }
    public void setNetProfit(Integer netProfit) { this.netProfit = netProfit; }
    public Double getEsgReductionKg() { return esgReductionKg; }
    public void setEsgReductionKg(Double esgReductionKg) { this.esgReductionKg = esgReductionKg; }
}
