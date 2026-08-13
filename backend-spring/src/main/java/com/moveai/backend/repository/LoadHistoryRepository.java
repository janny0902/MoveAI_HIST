package com.moveai.backend.repository;

import com.moveai.backend.entity.LoadHistory;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LoadHistoryRepository extends JpaRepository<LoadHistory, Long> {
    List<LoadHistory> findByTruckIdOrderByCreatedAtDesc(Long truckId);
    void deleteByTruckId(Long truckId);
}
