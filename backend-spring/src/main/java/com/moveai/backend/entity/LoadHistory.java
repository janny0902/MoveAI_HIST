package com.moveai.backend.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "load_history")
public class LoadHistory {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long truckId;
    private Long cargoRequestId;
    private String loadImageUrl;
    private Double remainingVolumePercent;
    private Double occupiedVolumePercent;
    private Integer income = 0;
    private Integer expense = 0;
    private Integer netProfit = 0;
    private Double esgReductionKg = 0.0;
    private String routeSummary;
    private Instant createdAt = Instant.now();

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getTruckId() { return truckId; }
    public void setTruckId(Long truckId) { this.truckId = truckId; }
    public Long getCargoRequestId() { return cargoRequestId; }
    public void setCargoRequestId(Long cargoRequestId) { this.cargoRequestId = cargoRequestId; }
    public String getLoadImageUrl() { return loadImageUrl; }
    public void setLoadImageUrl(String loadImageUrl) { this.loadImageUrl = loadImageUrl; }
    public Double getRemainingVolumePercent() { return remainingVolumePercent; }
    public void setRemainingVolumePercent(Double remainingVolumePercent) { this.remainingVolumePercent = remainingVolumePercent; }
    public Double getOccupiedVolumePercent() { return occupiedVolumePercent; }
    public void setOccupiedVolumePercent(Double occupiedVolumePercent) { this.occupiedVolumePercent = occupiedVolumePercent; }
    public Integer getIncome() { return income; }
    public void setIncome(Integer income) { this.income = income; }
    public Integer getExpense() { return expense; }
    public void setExpense(Integer expense) { this.expense = expense; }
    public Integer getNetProfit() { return netProfit; }
    public void setNetProfit(Integer netProfit) { this.netProfit = netProfit; }
    public Double getEsgReductionKg() { return esgReductionKg; }
    public void setEsgReductionKg(Double esgReductionKg) { this.esgReductionKg = esgReductionKg; }
    public String getRouteSummary() { return routeSummary; }
    public void setRouteSummary(String routeSummary) { this.routeSummary = routeSummary; }
    public Instant getCreatedAt() { return createdAt; }
}
