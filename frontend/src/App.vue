<template>
  <div
    class="kakao-app"
    :class="{
      'drive-lock': gate === 'app' && tab === 'drive',
      'cargo-lock': gate === 'app' && tab === 'cargo',
    }"
  >
    <!-- AI / 처리 로딩 -->
    <div v-if="busy.show" class="busy-overlay">
      <div class="busy-card shadow">
        <p class="busy-title">{{ busy.title }}</p>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: busy.percent + '%' }"></div>
        </div>
        <p class="busy-sub">{{ busy.percent }}% · {{ busy.hint }}</p>
      </div>
    </div>

    <!-- 실시간 알림 토스트 -->
    <div v-if="simOffer" class="toast toast-offer shadow" @click.stop>
      <strong>새 복화 물량</strong>
      <p>{{ simOffer.name || simOffer.code }}에 {{ Number(simOffer.fillPercent || 0).toFixed(1) }}% 물량을 적재할 수 있습니다.</p>
      <p class="toast-rem">계획 잔여 {{ simRemainingPercent().toFixed(1) }}%</p>
      <div class="toast-actions">
        <button type="button" class="k-btn outline sm" :disabled="busy.show" @click.stop="rejectSimOffer">거절</button>
        <button type="button" class="k-btn primary sm" :disabled="busy.show" @click.stop="acceptSimOffer">수락</button>
      </div>
    </div>
    <div v-else-if="toast" class="toast shadow" @click="toast = null">
      <strong>새 복화 물량</strong>
      <p>{{ toast }}</p>
    </div>

    <!-- 1) 로그인 -->
    <section v-if="gate === 'login'" class="gate p-16">
      <h1 class="gate-brand">moveAI</h1>
      <p class="gate-desc">차량번호와 전화번호로 접속합니다. (세션별 로그인)</p>
      <label class="field">차량번호
        <input v-model="loginForm.truckNumber" placeholder="예: 서울 12가 3456" />
      </label>
      <label class="field">전화번호
        <input v-model="loginForm.phone" placeholder="01012345678" inputmode="tel" />
      </label>
      <label class="field">기사 이름 (선택)
        <input v-model="loginForm.driverName" placeholder="김기사" />
      </label>
      <button class="k-btn primary w-full" :disabled="busy.show" @click="doLogin">접속</button>
    </section>

    <!-- 2) 차량 등록 -->
    <section v-else-if="gate === 'profile'" class="gate p-16">
      <h2>차량 정보 등록</h2>
      <p class="gate-desc">{{ me?.truckNumber }} · {{ me?.phone }}</p>
      <label class="field">기사 이름
        <input v-model="profileForm.driverName" />
      </label>
      <label class="field">차량 톤수
        <select v-model.number="profileForm.capacityTons">
          <option :value="1">1톤</option>
          <option :value="2.5">2.5톤</option>
          <option :value="5">5톤</option>
          <option :value="8">8톤</option>
          <option :value="11">11톤</option>
          <option :value="18">18톤</option>
          <option :value="25">25톤</option>
        </select>
      </label>
      <label class="field">차종
        <select v-model="profileForm.vehicleType">
          <option>윙바디</option>
          <option>카고</option>
          <option>탑차</option>
          <option>트레일러</option>
        </select>
      </label>
      <label class="field">현재 잔여공간 (%)
        <input v-model.number="profileForm.remainingVolumePercent" type="number" min="0" max="100" />
      </label>
      <button class="k-btn primary w-full" @click="doProfile">등록 완료</button>
    </section>

    <!-- 3) 출도착 (관리자와 동일 작업터미널) -->
    <section v-else-if="gate === 'route'" class="gate p-16">
      <h2>오늘 운행 경로</h2>
      <p class="gate-desc">작업터미널을 선택해 운행 경로를 정합니다</p>
      <p v-if="terminalsLoading" class="desc subtle">터미널 목록 불러오는 중...</p>
      <p v-else-if="!stations.length" class="desc subtle">
        터미널을 불러오지 못했습니다.
        <button class="link-btn" @click="loadTerminals({ force: true })">다시 시도</button>
      </p>
      <label class="field">출발 터미널
        <select v-model="routeForm.originCode" :disabled="!stations.length">
          <option disabled value="">선택</option>
          <option v-for="s in stations" :key="'ro-'+s.code" :value="s.code">{{ s.code }} · {{ s.name }}</option>
        </select>
      </label>
      <label class="field">도착 터미널
        <select v-model="routeForm.destinationCode" :disabled="!stations.length">
          <option disabled value="">선택</option>
          <option v-for="s in stations" :key="'rd-'+s.code" :value="s.code">{{ s.code }} · {{ s.name }}</option>
        </select>
      </label>
      <button class="k-btn primary w-full" :disabled="!stations.length || !routeForm.originCode || !routeForm.destinationCode" @click="doRoute">경로 저장 후 시작</button>
    </section>

    <!-- 메인 -->
    <template v-else>
      <header class="k-header">
        <div class="top-nav">
          <span class="brand">moveAI</span>
          <div class="me-chip">
            <span>{{ me?.driverName }}</span>
            <span class="sub">{{ me?.truckNumber }}</span>
          </div>
          <button class="demo-trigger" @click="openAdminVolume">+ 체적</button>
          <button class="link-btn" @click="logout">로그아웃</button>
        </div>
        <p class="route-bar" @click="gate = 'route'">
          {{ me?.originName || '출발' }} → {{ me?.destinationName || '도착' }}
          · 계획 적재 {{ plannedOccupiedDisplay }}%
          <span class="edit">변경</span>
        </p>
      </header>

      <main class="k-main">
        <!-- 복화: 지도 터미널 선택 / LLM 최적 배차 -->
        <section v-show="tab === 'cargo'" class="tab-cargo">
          <div class="cargo-top">
            <h3>복화 배차</h3>
            <div class="mode-inline">
              <button
                type="button"
                class="mode-chip sm"
                :class="{ on: dispatchMode === 'manual' }"
                @click="setDispatchMode('manual')"
              >수동</button>
              <button
                type="button"
                class="mode-chip sm"
                :class="{ on: dispatchMode === 'llm' }"
                @click="setDispatchMode('llm')"
              >LLM</button>
            </div>
            <button
              type="button"
              class="cart-badge"
              :class="{ empty: !dispatchCart.length, open: cartDockOpen }"
              @click="cartDockOpen = !cartDockOpen"
            >
              장바구니 {{ dispatchCart.length }}
              <span class="caret">{{ cartDockOpen ? '▼' : '▲' }}</span>
            </button>
          </div>

          <div class="cargo-map-stage">
            <div class="cargo-map-wrap">
              <div ref="cargoMapEl" class="cargo-map-canvas"></div>
              <div v-if="!cargoMapLoaded" class="map-placeholder cargo-map-ph">
                <p>{{ cargoMapMessage }}</p>
              </div>
              <div v-if="cartPreview" class="cart-route-overlay">
                <div class="direction">
                  <span class="dist">{{ Number(cartPreview.totalKm || 0).toFixed(1) }}km</span>
                  <span class="time" v-if="cartEta">{{ cartEta }} 도착</span>
                  <span class="time">{{ cartTime.durationMin }}분</span>
                </div>
                <p class="next-step">{{ shortRouteLabel(cartPreview.routeLabel) }}</p>
                <p class="route-line">
                  직행 {{ Number(cartPreview.baseKm || 0).toFixed(1) }}km
                  <template v-if="cartPreview.extraKm > 0"> · 우회 +{{ Number(cartPreview.extraKm).toFixed(1) }}km</template>
                  <template v-if="cartTime.extraMin > 0"> · +{{ cartTime.extraMin }}분</template>
                  <template v-if="cartLastAddedKm != null"> · 이번 +{{ cartLastAddedKm }}km</template>
                </p>
                <p v-if="cartPreview.pathSource === 'stops-only'" class="route-line" style="color:#ffb4b4">
                  도로 경로 없음 · 장바구니를 다시 열어 갱신하세요
                </p>
              </div>
              <button
                v-if="dispatchMode === 'llm'"
                class="k-btn primary cargo-opt-btn"
                :disabled="busy.show"
                @click="runOptimalPlan"
              >최적 배차 만들기</button>
            </div>

            <!-- 지도 위 그룹 리스트 오버레이 -->
            <div
              v-if="dispatchMode === 'manual' && selectedTerminal"
              class="cargo-map-sheet shadow"
            >
              <div class="sheet-head">
                <div>
                  <strong>{{ selectedTerminal.name }}</strong>
                  <span class="sub">{{ selectedTerminal.code }} · 출발 그룹</span>
                </div>
                <button class="link-btn" @click="clearTerminalSelection">닫기</button>
              </div>
              <div class="cargo-map-sheet-body">
                <div v-if="feedLoading" class="empty-box compact">불러오는 중...</div>
                <div v-else-if="!cargoItems.length" class="empty-box compact">이 터미널 출발 그룹이 없습니다.</div>
                <div v-for="item in cargoItems" :key="item.requestId" class="cargo-card shadow">
                  <div class="cc-route">{{ item.origin }} → {{ item.destination }}</div>
                  <div class="cc-meta">
                    <span>운송장 {{ item.waybillCount || 1 }}건</span>
                    <span>{{ cargoOptionLabel(item) }}</span>
                    <span>점유 {{ item.fillPercent ?? item.fillPercentOf11t }}%</span>
                  </div>
                  <div class="cc-meta">
                    <span class="plus">요금 {{ formatWon(item.proposedFee || item.netProfit) }}</span>
                    <span v-if="itemInCart(item)" class="plus">담김</span>
                  </div>
                  <div class="row gap-8 mt-8">
                    <button class="k-btn outline flex-1" @click="openOdItems(item)">목록</button>
                    <button
                      v-if="item.photoUrl"
                      class="k-btn outline flex-1"
                      @click="openCargoPhoto(item)"
                    >적재물보기</button>
                    <button
                      class="k-btn primary flex-2"
                      :disabled="itemInCart(item)"
                      @click="addToDispatchCart(item)"
                    >{{ itemInCart(item) ? '담김' : '담기' }}</button>
                  </div>
                </div>
                <div class="row gap-8 mt-8" v-if="cargoItems.length || feedPage > 0">
                  <button class="k-btn outline flex-1" :disabled="feedPage <= 0 || feedLoading" @click="prevFeedPage">이전</button>
                  <button class="k-btn outline flex-1" :disabled="!feedHasMore || feedLoading" @click="nextFeedPage">다음</button>
                </div>
              </div>
            </div>

            <div
              v-if="dispatchMode === 'llm' && optimalPlan"
              class="cargo-map-sheet shadow"
            >
              <div class="sheet-head">
                <div>
                  <strong>LLM 추천</strong>
                  <span class="sub">{{ optimalPlan.llmSource || 'ai' }}</span>
                </div>
                <button class="link-btn" @click="optimalPlan = null">닫기</button>
              </div>
              <div class="cargo-map-sheet-body">
                <p class="briefing-box">{{ optimalPlan.briefing }}</p>
                <div class="cc-meta mb-8" v-if="optimalPlan.summary">
                  <span class="plus">합계 {{ formatWon(optimalPlan.summary.totalNetProfit) }}</span>
                  <span>+{{ optimalPlan.summary.totalExtraKm }}km</span>
                  <span>~{{ optimalPlan.summary.totalExtraMinutes }}분</span>
                </div>
                <div v-for="item in (optimalPlan.recommended || [])" :key="item.requestId" class="cargo-card shadow">
                  <div class="cc-route">{{ item.origin }} → {{ item.destination }}</div>
                  <div class="cc-meta">
                    <span>추가 +{{ item.extraDistanceKm }}km</span>
                    <span>점유 {{ item.fillPercent ?? item.fillPercentOf11t }}%</span>
                    <span class="plus">{{ formatWon(item.netProfit) }}</span>
                  </div>
                </div>
                <button
                  class="k-btn primary w-full mt-8"
                  :disabled="!(optimalPlan.recommended?.length || optimalPlan.requestIds?.length) || busy.show"
                  @click="addOptimalPlanToCart"
                >장바구니에 담기 ({{ optimalPlan.recommended?.length || optimalPlan.requestIds?.length || 0 }}건)</button>
              </div>
            </div>
          </div>

          <!-- 하단: 장바구니 토글 독 -->
          <div class="cargo-dock shadow" :class="{ collapsed: !cartDockOpen }">
            <button
              type="button"
              class="cargo-dock-toggle"
              @click="cartDockOpen = !cartDockOpen"
            >
              <span>
                <strong>장바구니 {{ dispatchCart.length }}건</strong>
                <span class="sub" v-if="cartPreview && dispatchCart.length">
                  {{ cartPreview.totalKm }}km
                  <template v-if="cartPreview.netProfit != null"> · {{ formatWon(cartPreview.netProfit) }}</template>
                </span>
                <span class="sub" v-else>터미널 핀 → 담기</span>
              </span>
              <span class="caret">{{ cartDockOpen ? '접기 ▼' : '펼치기 ▲' }}</span>
            </button>

            <div v-show="cartDockOpen" class="cargo-dock-body">
              <div class="sheet-head" v-if="dispatchCart.length">
                <div class="cc-meta" v-if="cartPreview">
                  <span>직행 {{ cartPreview.baseKm }}km</span>
                  <span class="plus">합계 {{ cartPreview.totalKm }}km</span>
                  <span v-if="cartPreview.extraKm > 0">+{{ cartPreview.extraKm }}km</span>
                </div>
                <button class="link-btn" @click="clearDispatchCart">비우기</button>
              </div>
              <div v-if="dispatchCart.length" class="cargo-dock-list">
                <div v-for="(c, idx) in dispatchCart" :key="c.odGroupId" class="cart-row">
                  <div>
                    <div class="cc-route">{{ idx + 1 }}. {{ c.origin }} → {{ c.destination }}</div>
                    <div class="cc-meta">
                      <span>{{ cargoOptionLabel(c) }}</span>
                      <span v-if="c.addedKm != null" class="plus">경로 +{{ c.addedKm }}km</span>
                    </div>
                  </div>
                  <button class="link-btn" @click="removeFromCart(c.odGroupId)">빼기</button>
                </div>
              </div>
              <p v-else class="cargo-dock-empty">터미널 핀 → 그룹 담기 · 내비 경로가 지도에 표시됩니다</p>
            </div>

            <button
              class="k-btn primary w-full cargo-confirm-btn"
              :disabled="!dispatchCart.length || busy.show"
              @click="confirmDispatchCart"
            >배차 확정{{ dispatchCart.length ? ` (${dispatchCart.length}건)` : '' }}</button>
          </div>
        </section>

        <!-- 운행/지도 -->
        <section v-show="tab === 'drive'" class="tab-drive">
          <!-- 첫 화면: 지도 80% + 출도착 20% -->
          <div class="drive-stage">
            <div class="map-container">
              <div ref="mapEl" class="map-canvas"></div>
              <div v-if="!mapLoaded" class="map-placeholder">
                <p>{{ mapMessage }}</p>
                <span class="hint">{{ mapHint }}</span>
              </div>
              <div v-if="naviInfo" class="navi-overlay">
                <div class="direction">
                  <span class="dist">{{ naviInfo.distance }}km</span>
                  <span class="time" v-if="driveEta">{{ driveEta }} 도착</span>
                  <span class="time">{{ driveTime.durationMin }}분</span>
                </div>
                <p class="next-step">{{ naviInfo.nextStep }}</p>
                <p class="route-line">{{ naviInfo.route }}</p>
                <p class="route-line" v-if="driveTime.extraMin > 0">우회 +{{ driveTime.extraMin }}분</p>
              </div>
              <button
                type="button"
                class="sim-step-btn"
                :disabled="!canSimStep"
                title="경로 20km 전진"
                @click="stepDriverAlongRoute"
              >›</button>
            </div>

            <div class="drive-dock">
              <div v-if="activeTrip" class="stop-panel shadow">
                <div class="stop-now">
                  <span class="stop-phase">{{ tripPhaseLabel }}</span>
                  <span class="stop-idx">{{ activeTrip.stopIndex + 1 }}/{{ activeTrip.stops.length }}</span>
                </div>
                <div class="stop-od">
                  <div class="stop-od-row">
                    <span class="od-tag from">출발지</span>
                    <strong>{{ tripFromName }}</strong>
                  </div>
                  <div class="stop-od-arrow" aria-hidden="true">↓</div>
                  <div class="stop-od-row">
                    <span class="od-tag to">도착지</span>
                    <strong>{{ tripToName }}</strong>
                  </div>
                </div>
                <p class="stop-step-hint">{{ driveStepHint }}</p>
                <div class="stop-actions">
                  <label
                    class="k-btn sm photo-btn"
                    :class="photoBtnClass"
                    :aria-disabled="!canPhoto || busy.show"
                  >
                    상차 사진
                    <input
                      v-if="canPhoto && !busy.show"
                      type="file"
                      accept="image/*"
                      hidden
                      @change="onImageUpload"
                    />
                  </label>
                  <button
                    type="button"
                    class="k-btn sm"
                    :class="canDepart ? 'primary' : 'outline'"
                    v-if="activeTrip.phase !== 'DONE'"
                    :disabled="busy.show || !canDepart"
                    @click="departFromStop"
                  >{{ departButtonLabel }}</button>
                  <button
                    type="button"
                    class="k-btn sm"
                    :class="canArrive ? 'primary' : 'outline'"
                    :disabled="busy.show || !canArrive"
                    @click="arriveAtStop"
                  >도착지에 도착</button>
                </div>
              </div>
              <div v-else class="stop-panel shadow muted">
                <p class="stop-hint" style="margin:0">복화 탭에서 배차 확정 후 출도착이 표시됩니다.</p>
              </div>
            </div>
          </div>

          <!-- 스크롤 아래: 적재 UI · 운행 완료 -->
          <div class="drive-more">
            <CargoFillView
              :capacity-cbm="truckCapacityM3"
              :loaded-cbm="displayLoadedCbm"
              :fill-pct="displayFillPct"
              :cargo-width-m="truckDims.widthM"
              :cargo-length-m="truckDims.lengthM"
              :cargo-height-m="truckDims.heightM"
              :model-label="truckModelLabel"
              :measured="spaceMeasured"
              :terminal-loads="terminalLoadsForView"
              :truck-tons="me?.capacityTons || 11"
              :truck-number="me?.truckNumber || ''"
              :status-text="truckStatusText"
              :status-kind="truckStatus"
              :planned-fill-pct="plannedOccupied"
            />

            <div v-if="showCompleteTripBtn || guide" class="drive-actions">
              <button
                v-if="showCompleteTripBtn"
                class="k-btn primary w-full"
                :disabled="busy.show"
                @click="completeTripAndGoLedger"
              >운행 완료</button>
              <p v-if="guide" class="guide">{{ guide }}</p>
            </div>
          </div>

          <transition name="slide-up">
            <div v-if="proposal" class="k-modal-bottom shadow">
              <div class="handle"></div>
              <div class="proposal-header">
                <span class="badge-new">NEW</span>
                <h3>복화 알림</h3>
                <span class="badge-race">선착순</span>
              </div>
              <div class="briefing-box">"{{ proposal.briefing }}"</div>
              <ul class="mini-stats">
                <li>{{ proposal.origin }} → {{ proposal.destination }}</li>
                <li>우회 +{{ proposal.extraDistanceKm }}km · 유류 {{ formatWon(proposal.extraFuelCost) }}</li>
                <li>ESG {{ proposal.esgReductionKg }}kg · {{ proposal.fillPercentOf11t }}%</li>
              </ul>
              <div class="price-row">
                <span>예상 순이익</span>
                <span class="price">{{ formatWon(proposal.netProfit) }}</span>
              </div>
              <div class="row gap-8">
                <button class="k-btn gray flex-1" @click="dismissProposal">닫기</button>
                <button class="k-btn primary flex-2" @click="acceptProposal({})">수락</button>
              </div>
            </div>
          </transition>
        </section>

        <!-- 정산 -->
        <section v-if="tab === 'ledger'" class="tab-content p-16">
          <div class="k-card shadow mb-16">
            <h3>나의 운행 정산</h3>
            <p class="desc subtle mb-8">배차 건별로 터미널·물량·금액을 확인할 수 있습니다.</p>

            <div class="ledger-grid" v-if="ledger">
              <div class="item"><label>합계 수입</label><p class="val plus">{{ formatWon(ledger.totalIncome) }}</p></div>
              <div class="item"><label>합계 지출</label><p class="val">{{ formatWon(ledger.totalExpense) }}</p></div>
              <div class="item"><label>순수익</label><p class="val plus">{{ formatWon(ledger.netProfit) }}</p></div>
              <div class="item"><label>ESG</label><p class="val esg">{{ ledger.dailyEsgKg }}kg</p></div>
            </div>

            <h4 class="ledger-sub">건별 내역 ({{ ledger?.entryCount || ledger?.entries?.length || 0 }}건)</h4>
            <div class="ledger-list" v-if="ledger?.entries?.length">
              <article class="ledger-row" v-for="(e, idx) in ledger.entries" :key="e.id || idx">
                <div class="ledger-row-head">
                  <span class="ledger-no">#{{ ledger.entries.length - idx }}</span>
                  <span class="ledger-time" v-if="e.createdAt">{{ formatLedgerTime(e.createdAt) }}</span>
                </div>
                <div class="route">{{ e.title || e.route }}</div>
                <div class="ledger-od">
                  <span><i class="od-tag from">상차</i>{{ e.origin || '?' }}</span>
                  <span class="arrow">→</span>
                  <span><i class="od-tag to">하차</i>{{ e.destination || '?' }}</span>
                </div>
                <ul class="ledger-meta">
                  <li v-if="e.boxCount">물량 {{ e.boxCount }}박스</li>
                  <li v-if="e.fillPercent != null">점유 {{ e.fillPercent }}%</li>
                  <li v-if="e.volumeM3 != null">체적 {{ e.volumeM3 }} m³</li>
                  <li v-if="e.esgReductionKg != null">ESG {{ e.esgReductionKg }}kg</li>
                </ul>
                <div class="amt">
                  <span class="plus">운임 +{{ formatWon(e.income) }}</span>
                  <span class="minus">유류 {{ formatWon(e.expense) }}</span>
                  <span class="net">순 {{ formatWon(e.netProfit) }}</span>
                </div>
              </article>
            </div>
            <p v-else class="desc subtle">수락·배차된 건이 없습니다. 복화 배차 후 운행을 완료하면 여기에 쌓입니다.</p>
          </div>
        </section>

        <div v-show="tab !== 'cargo'" class="card log-container shadow">
          <div class="log-header" @click="showLogs = !showLogs">
            <span>처리 과정</span>
            <span class="log-toggle">{{ showLogs ? '접기 ▲' : '펼치기 ▼' }}</span>
          </div>
          <div v-if="showLogs" class="log-content" ref="logBox">
            <p v-for="(log, i) in logs" :key="i">> {{ log }}</p>
          </div>
        </div>
      </main>

      <nav class="k-bottom-nav shadow">
        <div class="nav-item" :class="{ active: tab === 'cargo' }" @click="tab = 'cargo'; nextTick(() => initCargoMap())">
          <span class="label">배차목록</span>
        </div>
        <div class="nav-item" :class="{ active: tab === 'drive' }" @click="goDrive">
          <span class="label">운행</span>
        </div>
        <div class="nav-item" :class="{ active: tab === 'ledger' }" @click="tab = 'ledger'; loadLedger()">
          <span class="label">정산</span>
        </div>
      </nav>
    </template>

    <!-- OD 그룹 내 박스 목록 -->
    <div v-if="odItemsModal.show" class="k-overlay" @click.self="odItemsModal.show = false">
      <div class="k-modal-center shadow">
        <h3>그룹 목록</h3>
        <p class="desc">{{ odItemsModal.origin }} → {{ odItemsModal.destination }}</p>
        <p v-if="odItemsModal.aggregateOnly" class="desc subtle">집계만 있는 그룹입니다.</p>
        <div v-if="odItemsModal.loading" class="empty-box">불러오는 중...</div>
        <div v-else class="od-item-list">
          <div v-for="row in odItemsModal.items" :key="row.id" class="od-item-row">
            <div class="oid">{{ row.externalCargoId || ('#' + row.id) }}</div>
            <div class="ometa">
              {{ row.productName || row.productCode || '화물' }}
              {{ row.boxCount || 1 }} · {{ row.volumeM3 }}m³ · {{ formatWon(row.freightKrw) }}
            </div>
            <div class="ostatus">{{ row.status }}</div>
            <button
              v-if="row.photoUrl"
              class="link-btn"
              type="button"
              @click="openCargoPhoto({ photoUrl: row.photoUrl, origin: odItemsModal.origin, destination: odItemsModal.destination })"
            >적재물보기</button>
          </div>
          <div v-if="!odItemsModal.items.length && !odItemsModal.aggregateOnly" class="empty-box">항목이 없습니다.</div>
        </div>
        <button class="k-btn gray w-full mt-16" @click="odItemsModal.show = false">닫기</button>
      </div>
    </div>

    <!-- 적재물 사진 -->
    <div v-if="cargoPhotoModal.show" class="k-overlay" @click.self="cargoPhotoModal.show = false">
      <div class="k-modal-center shadow cargo-photo-modal">
        <h3>적재물보기</h3>
        <p class="desc" v-if="cargoPhotoModal.title">{{ cargoPhotoModal.title }}</p>
        <img
          v-if="cargoPhotoModal.url"
          :src="cargoPhotoModal.url"
          alt="등록 적재 사진"
          class="cargo-photo-img"
        />
        <p v-else class="empty-box">사진이 없습니다.</p>
        <button class="k-btn gray w-full mt-16" @click="cargoPhotoModal.show = false">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import CargoFillView from './components/CargoFillView.vue'

const SESSION_KEY = 'moveai_session'
const TRIP_KEY_PREFIX = 'moveai_active_trip_'
const DEMO_RESET_AT_KEY = 'moveai_demo_reset_at'
const DEMO_EPOCH_KEY = 'moveai_demo_epoch'

const gate = ref('login') // login | profile | route | app
const tab = ref('cargo')
const me = ref(null)
const stations = ref([])
const terminalsLoading = ref(false)
const logs = ref([])
const showLogs = ref(false)
const logBox = ref(null)
const toast = ref(null)
const busy = ref({ show: false, title: '', hint: '', percent: 0 })
let busyTimer = null

const loginForm = ref({ truckNumber: '', phone: '', driverName: '' })
const profileForm = ref({ driverName: '', capacityTons: 11, vehicleType: '윙바디', remainingVolumePercent: 100 })
const routeForm = ref({ originCode: '', destinationCode: '' })
const feedPage = ref(0)
const feedHasMore = ref(false)
const feedCandidateCount = ref(0)
const feedLoading = ref(false)
const dispatchMode = ref('manual') // manual | llm
const selectedTerminal = ref(null)
const optimalPlan = ref(null)
const cargoMapEl = ref(null)
const cargoMapInstance = ref(null)
const cargoMapLoaded = ref(false)
const cargoMapMessage = ref('지도 준비')
const cargoMapMarkers = ref([])
const cargoMapFitted = ref(false)
const cargoTerminals = ref([]) // 물량 있는 터미널(코드 유일)
const dispatchCart = ref([]) // { odGroupId, requestId, origin, destination, ... }
const cartDockOpen = ref(false)
const cartPreview = ref(null)
const cartLastAddedKm = ref(null)
let cargoRouteLine = null
let cargoRouteMarkers = []

const remaining = ref(100)
const occupied = ref(0)
const spaceMeasured = ref(false)
const occupancyGrid = ref(null)
const truckStatus = ref('IDLE')
const truckStatusText = ref('대기 중')
const proposal = ref(null)
const cargoItems = ref([])
const lastSeenRequestId = ref(0)
const dismissed = ref(new Set())
const ledger = ref(null)
const guide = ref('')
const naviInfo = ref(null)
const pendingDriveRoute = ref(null)
/** 배차 확정 후 운행 상태: 경유 스톱 · 터미널별 계획 적재 · 출발/도착 */
const activeTrip = ref(null)
const simKmAlong = ref(0)
const simPos = ref(null)
const simAtEnd = ref(false)
const simAlertedCodes = ref([])
const simAcceptedCodes = ref([])
const simRejectedCodes = ref([])
const simOffer = ref(null)
const simNearby = ref([])
const simOverlays = ref([])
const SIM_STEP_KM = 20
const SIM_RADIUS_KM = 20

const canSimStep = computed(() => {
  if (simAtEnd.value) return false
  const path = driveSimPath()
  return path.length >= 2
})

const TERM_COLORS = [
  '#2f80ed', '#27ae60', '#f2994a', '#9b51e0',
  '#eb5757', '#56ccf2', '#219653', '#f2c94c',
]

/** 톤수 → 대략 적재함 치수 (등각 격자 비율용) */
const DIM_BY_TONS = {
  1: { widthM: 1.67, lengthM: 2.83, heightM: 1.81 },
  2.5: { widthM: 1.8, lengthM: 4.2, heightM: 2.0 },
  5: { widthM: 2.1, lengthM: 5.5, heightM: 2.2 },
  8: { widthM: 2.3, lengthM: 7.2, heightM: 2.3 },
  11: { widthM: 2.35, lengthM: 9.3, heightM: 2.45 },
  18: { widthM: 2.4, lengthM: 11.0, heightM: 2.5 },
  25: { widthM: 2.45, lengthM: 13.0, heightM: 2.6 },
}

const truckCapacityM3 = computed(() => Number(me.value?.capacityM3 || 30.545))
const truckDims = computed(() => {
  const t = Number(me.value?.capacityTons || 11)
  return DIM_BY_TONS[t] || DIM_BY_TONS[11]
})
const truckModelLabel = computed(() => {
  const tons = me.value?.capacityTons || 11
  const vt = me.value?.vehicleType || '윙바디'
  return `${tons}톤 ${vt}`
})
const loadedCbm = computed(() =>
  Math.round((truckCapacityM3.value * (Number(occupied.value) || 0) / 100) * 100) / 100
)

/** 경부축 대략 순서 (남→북). 백엔드 DispatchCartService.corridorIndex 와 맞춤 */
function corridorIndex(code) {
  if (code == null) return 50
  const c = String(code).trim()
  const fixed = { '200': 0, '201': 1, '300': 20, '308': 22, '500': 40, '501': 42, '503': 44, '514': 46, '001': 90, '008': 92 }
  if (fixed[c] != null) return fixed[c]
  const n = Number(c)
  if (!Number.isFinite(n)) return 50
  if (n <= 50) return 90
  if (n >= 200 && n < 300) return 0
  if (n >= 300 && n < 400) return 20
  if (n >= 500 && n < 600) return 40
  return 50
}

function terminalLat(code) {
  const s = stationByCode(code)
  return s?.lat != null ? Number(s.lat) : 0
}

/** 기사 O→D 진행 방향으로 상차 터미널/화물 정렬 */
function compareAlongDriver(codeA, codeB) {
  const origin = me.value?.originCode || '200'
  const dest = me.value?.destinationCode || '001'
  const northbound = corridorIndex(dest) >= corridorIndex(origin)
  const cmp = corridorIndex(codeA) - corridorIndex(codeB)
  if (cmp !== 0) return northbound ? cmp : -cmp
  const latCmp = terminalLat(codeA) - terminalLat(codeB)
  if (latCmp !== 0) return northbound ? latCmp : -latCmp
  return String(codeA || '').localeCompare(String(codeB || ''), 'ko')
}

/** 장바구니 또는 확정 운행의 터미널(상차지)별 계획 적재 — 진행 방향 순 */
function aggregateTerminalLoads(items) {
  const map = new Map()
  for (const it of items || []) {
    const code = String(it.originCode || it.code || it.origin || '').trim() || '_'
    const name = it.origin || it.name || it.terminalName || code
    const fill = Number(it.fillPercent ?? it.fillPercentOf11t ?? 0) || 0
    if (fill <= 0) continue
    const prev = map.get(code)
    if (prev) {
      prev.fillPercent += fill
      if (!prev.photoUrl && it.photoUrl) prev.photoUrl = it.photoUrl
    } else {
      map.set(code, {
        code,
        name,
        fillPercent: fill,
        photoUrl: it.photoUrl || null,
      })
    }
  }
  return [...map.values()]
    .sort((a, b) => compareAlongDriver(a.code, b.code))
    .map((t, idx) => ({
      ...t,
      fillPercent: Math.round(t.fillPercent * 100) / 100,
      color: TERM_COLORS[idx % TERM_COLORS.length],
    }))
}

function sortItemsAlongDriver(items) {
  return [...(items || [])].sort((a, b) =>
    compareAlongDriver(
      a.originCode || a.code || '',
      b.originCode || b.code || '',
    ))
}

const plannedTerminalLoads = computed(() => {
  if (activeTrip.value?.loads?.length) return activeTrip.value.loads
  return aggregateTerminalLoads(dispatchCart.value)
})

const plannedOccupied = computed(() =>
  Math.round(plannedTerminalLoads.value.reduce((s, t) => s + Number(t.fillPercent || 0), 0) * 100) / 100
)

const plannedOccupiedDisplay = computed(() =>
  Number(plannedOccupied.value || 0).toFixed(1)
)

const clockTick = ref(Date.now())
let clockTimer = null

function routeTimeParts(src) {
  if (!src) return { durationMin: 0, extraMin: 0 }
  const duration = Number(src.durationMin ?? src.duration)
  const extra = Number(src.extraMinutes ?? src.extraMin)
  if (Number.isFinite(duration) && duration > 0) {
    return {
      durationMin: Math.round(duration),
      extraMin: Number.isFinite(extra) ? Math.max(0, Math.round(extra)) : 0,
    }
  }
  return {
    durationMin: Number.isFinite(extra) ? Math.round(extra) : 0,
    extraMin: 0,
  }
}

function etaFromNow(durationMin, now = clockTick.value) {
  const m = Number(durationMin)
  if (!Number.isFinite(m) || m <= 0) return ''
  const d = new Date(now + m * 60000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

const cartTime = computed(() => routeTimeParts(cartPreview.value))
const cartEta = computed(() => etaFromNow(cartTime.value.durationMin))
const driveTime = computed(() => routeTimeParts(naviInfo.value))
const driveEta = computed(() => etaFromNow(driveTime.value.durationMin))

function startClockTick() {
  stopClockTick()
  clockTick.value = Date.now()
  clockTimer = setInterval(() => { clockTick.value = Date.now() }, 30000)
}

function stopClockTick() {
  if (clockTimer) {
    clearInterval(clockTimer)
    clockTimer = null
  }
}

function isOriginStop(t, idx = t?.stopIndex) {
  if (!t?.stops?.length) return false
  const i = Number(idx)
  if (i === 0) return true
  const s = t.stops[i]
  return String(s?.role || '') === '출발'
}

function isPickupStop(t, idx = t?.stopIndex) {
  if (!t?.stops?.length) return false
  if (isOriginStop(t, idx) || isFinalStopAt(t, idx)) return false
  return true
}

function isFinalStopAt(t, idx) {
  if (!t?.stops?.length) return false
  const i = Number(idx)
  if (i >= t.stops.length - 1) return true
  return String(t.stops[i]?.role || '') === '도착'
}

function cargoSegmentsForView(list) {
  return (list || []).filter((x) => Number(x.fillPercent) >= 0)
}

function lookupLoad(list, stop, idx) {
  const code = String(stop?.code || '').trim()
  const name = String(stop?.name || stop?.terminalName || '').trim()
  return (list || []).find((x) => {
    if (x.stopIndex != null && Number(x.stopIndex) === idx) return true
    if (code && x.code && String(x.code) === code) return true
    if (name && x.name && String(x.name) === name) return true
    return false
  }) || null
}

/** 운행 경유(출발·경유·도착)를 그대로 쌓고, 상차 사진이 있는 칸만 실측을 붙인다 */
const terminalLoadsForView = computed(() => {
  const planned = plannedTerminalLoads.value || []
  const measured = cargoSegmentsForView(activeTrip.value?.measuredLoads)
  const stops = activeTrip.value?.stops || []
  if (stops.length) {
    return stops.map((s, idx) => {
      const p = lookupLoad(planned, s, idx)
      const m = lookupLoad(measured, s, idx)
      const plannedPct = p != null ? Math.round(Number(p.fillPercent || 0) * 100) / 100 : 0
      const measuredPct = m != null ? Math.round(Number(m.fillPercent || 0) * 100) / 100 : null
      const role = s.role || (idx === 0 ? '출발' : (idx === stops.length - 1 ? '도착' : '경유'))
      return {
        name: s.name || s.terminalName || `${idx + 1}번`,
        code: s.code || `stop-${idx}`,
        role,
        stopIndex: idx,
        plannedPercent: plannedPct,
        measuredPercent: measuredPct,
        fillPercent: measuredPct != null ? measuredPct : 0,
        color: TERM_COLORS[idx % TERM_COLORS.length],
      }
    })
  }
  return planned.map((p, idx) => ({
    ...p,
    role: '경유',
    plannedPercent: Math.round(Number(p.fillPercent || 0) * 100) / 100,
    measuredPercent: null,
    fillPercent: 0,
    color: p.color || TERM_COLORS[idx % TERM_COLORS.length],
  }))
})

/** 상차 사진 실측 합계만 채움 */
const displayFillPct = computed(() =>
  spaceMeasured.value ? Number(occupied.value) || 0 : 0
)
const displayLoadedCbm = computed(() =>
  Math.round((truckCapacityM3.value * displayFillPct.value / 100) * 100) / 100
)

/** 현재 정차에서 상차 사진 → 이번 터미널 실측분(Δ)을 색 세그먼트로 누적 */
function recordMeasuredLoadAtStop(newOccupiedPct) {
  const total = Math.max(0, Math.min(100, Number(newOccupiedPct) || 0))
  const t = activeTrip.value
  if (!t) return
  if (!Array.isArray(t.measuredLoads)) t.measuredLoads = []

  const stopIdx = t.stopIndex
  // 출발지(공차)는 목록에 넣지 않음
  if (isOriginStop(t, stopIdx)) {
    t.measuredLoads = t.measuredLoads.filter((x) => Number(x.stopIndex) !== 0)
    return
  }

  let loads = t.measuredLoads.filter((x) => Number(x.stopIndex) < stopIdx && Number(x.stopIndex) !== 0)
  const baseBefore = loads.reduce((s, x) => s + Number(x.fillPercent || 0), 0)
  let delta = Math.round(Math.max(0, total - baseBefore) * 100) / 100

  const stop = t.stops?.[stopIdx] || {}
  const planned = (t.loads || []).find((l) =>
    l.code && stop.code && String(l.code) === String(stop.code)
  ) || (t.loads || []).find((l) =>
    l.name && stop.name && String(l.name) === String(stop.name)
  )
  const color = planned?.color || TERM_COLORS[loads.length % TERM_COLORS.length]
  const name = stop.name || stop.terminalName || planned?.name || `${stopIdx + 1}번 경유`

  loads.push({
    stopIndex: stopIdx,
    code: stop.code || planned?.code || `stop-${stopIdx}`,
    name,
    role: stop.role || '경유',
    fillPercent: delta,
    color,
  })

  const sum = loads.reduce((s, x) => s + Number(x.fillPercent || 0), 0)
  if (loads.length && Math.abs(sum - total) > 0.05) {
    const last = loads[loads.length - 1]
    const others = sum - Number(last.fillPercent || 0)
    last.fillPercent = Math.round(Math.max(0, total - others) * 100) / 100
  }
  t.measuredLoads = loads
}

const currentStopName = computed(() => {
  const t = activeTrip.value
  if (!t?.stops?.length) return '-'
  const s = t.stops[Math.min(t.stopIndex, t.stops.length - 1)]
  return s?.name || s?.terminalName || `${t.stopIndex + 1}번 경유`
})

const nextStopName = computed(() => {
  const t = activeTrip.value
  if (!t?.stops?.length) return '-'
  if (t.stopIndex >= t.stops.length - 1) return '최종'
  const s = t.stops[t.stopIndex + 1]
  return s?.name || s?.terminalName || `${t.stopIndex + 2}번 경유`
})

/** 정차 중: 현재=출발지, 다음=도착지 / 이동 중: 떠난곳=출발지, 가는곳=도착지 */
const tripFromName = computed(() => currentStopName.value)
const tripToName = computed(() => {
  const t = activeTrip.value
  if (!t) return '-'
  if (t.phase === 'DONE') return currentStopName.value
  if (t.stopIndex >= t.stops.length - 1) return '(최종)'
  return nextStopName.value
})

const isFinalStop = computed(() => isFinalStopAt(activeTrip.value, activeTrip.value?.stopIndex))

/** 최종 도착지에서만 운행 완료 → 정산 이동 */
const showCompleteTripBtn = computed(() => {
  const t = activeTrip.value
  if (!t || !isFinalStop.value) return false
  return t.phase === 'AT_STOP' || t.phase === 'DONE'
})

const needPhotoBeforeDepart = computed(() => {
  const t = activeTrip.value
  // 출발지 공차 출발은 사진 없이 가능. 경유 상차지에서만 상차 사진 필수
  return !!(t && t.phase === 'AT_STOP' && !t.photoOk && isPickupStop(t))
})

/** 이동 중 → 도착 버튼만 */
const canArrive = computed(() => activeTrip.value?.phase === 'EN_ROUTE')

/** 정차 중·최종 아닌 곳 → 상차 사진 (경유는 필수, 출발지는 선택) */
const canPhoto = computed(() => {
  const t = activeTrip.value
  if (!t || t.phase !== 'AT_STOP' || isFinalStop.value) return false
  return true
})

/** 정차 중 + (상차 필수면 사진 완료) → 출발/운행완료 */
const canDepart = computed(() => {
  const t = activeTrip.value
  if (!t || t.phase !== 'AT_STOP') return false
  if (needPhotoBeforeDepart.value) return false
  return true
})

const photoBtnClass = computed(() => {
  if (!canPhoto.value) return 'outline is-disabled'
  if (needPhotoBeforeDepart.value) return 'primary need'
  if (activeTrip.value?.photoOk) return 'outline done'
  return 'outline'
})

const driveStepHint = computed(() => {
  const t = activeTrip.value
  if (!t || t.phase === 'DONE') return '운행이 끝났습니다'
  if (canArrive.value) return '① 이동 중 → 「도착지에 도착」'
  if (needPhotoBeforeDepart.value) return '① 정차 중 → 「상차 사진」등록 후 출발'
  if (canDepart.value && isFinalStop.value) return '① 최종 도착 → 「운행 완료」'
  if (canDepart.value && canPhoto.value) {
    return t.photoOk
      ? '① 상차 완료 → 「도착지로 출발」'
      : '① 정차 중 → 「도착지로 출발」(상차 사진 선택)'
  }
  if (canDepart.value) return '① 정차 중 → 「도착지로 출발」'
  return ''
})

const departButtonLabel = computed(() => {
  if (isFinalStop.value) return '운행 완료'
  return '도착지로 출발'
})

/** 운행 완료 → 공차·계획/실측 초기화(정산은 유지) → 다음 배차 가능 */
async function completeTripAndGoLedger() {
  const truckId = me.value?.truckId
  startBusy('운행 완료', '적재를 비우고 정산을 불러오는 중...')
  try {
    if (activeTrip.value) {
      activeTrip.value = { ...activeTrip.value, phase: 'DONE' }
    }
    if (truckId) {
      try {
        const { data } = await axios.post('/api/dispatch/truck/clear-space', null, {
          params: { truckId },
        })
        applyMe({
          ...me.value,
          ...data,
          remainingVolumePercent: 100,
          occupiedVolumePercent: 0,
          status: 'IDLE',
          activeRequestId: null,
        })
      } catch (e) {
        addLogs('공차 초기화 스킵: ' + (e.response?.data?.message || e.message || e))
        remaining.value = 100
        occupied.value = 0
        if (me.value) {
          me.value = { ...me.value, remainingVolumePercent: 100, occupiedVolumePercent: 0, status: 'IDLE' }
        }
      }
    }
    // 운행·계획 적재·실측·내비·장바구니만 비움 (정산 ledger는 유지)
    activeTrip.value = null
    spaceMeasured.value = false
    occupied.value = 0
    remaining.value = 100
    occupancyGrid.value = null
    naviInfo.value = null
    pendingDriveRoute.value = null
    lastDrawnRoute = null
    resetSimProgress(true)
    proposal.value = null
    optimalPlan.value = null
    guide.value = ''
    cargoItems.value = []
    selectedTerminal.value = null
    truckStatus.value = 'IDLE'
    truckStatusText.value = '대기 중'
    clearActiveTripStorage(truckId)
    if (polyline.value) {
      try { polyline.value.setMap(null) } catch (_) {}
      polyline.value = null
    }
    try { clearMarkers() } catch (_) {}
    try { clearSimOverlays() } catch (_) {}
    await clearDispatchCart()
    await loadLedger()
    await loadCargoTerminals()
    addLogs('운행 완료 · 공차 초기화 · 다음 배차 가능')
    toast.value = '운행 완료 · 적재 초기화됨 · 배차목록에서 다음 운행을 잡으세요'
    setTimeout(() => { toast.value = null }, 4000)
    tab.value = 'ledger'
  } finally {
    endBusy()
  }
}

function formatLedgerTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16)
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch (_) {
    return String(iso).slice(0, 16)
  }
}

const tripPhaseLabel = computed(() => {
  const p = activeTrip.value?.phase
  if (p === 'EN_ROUTE') return '이동 중'
  if (p === 'DONE') return '운행 완료'
  return '정차 중'
})

function startActiveTrip({ stops = [], cartItems = [], proposalItem = null } = {}) {
  const items = cartItems.length
    ? cartItems
    : (proposalItem ? [proposalItem] : [])
  const loads = aggregateTerminalLoads(items)
  const stopList = (stops || []).map((s) => ({ ...s }))
  if (!stopList.length && me.value) {
    stopList.push(
      { name: me.value.originName || '출발', code: me.value.originCode },
      { name: me.value.destinationName || '도착', code: me.value.destinationCode },
    )
  }
  activeTrip.value = {
    stops: stopList,
    loads,
    measuredLoads: [],
    stopIndex: 0,
    phase: 'AT_STOP',
    photoOk: false,
  }
  resetSimProgress(false)
  truckStatus.value = 'LOADING'
  truckStatusText.value = '상차 대기'
  spaceMeasured.value = false
  occupied.value = 0
  addLogs(`운행 시작 · 계획 적재 ${plannedOccupied.value}% · 경유 ${stopList.length}곳`)
  saveActiveTrip()
  nextTick(() => {
    placeSimOverlays()
    bootstrapSimOffer()
  })
}

function departFromStop() {
  const t = activeTrip.value
  if (!t || t.phase !== 'AT_STOP') return
  const atFinal = t.stopIndex >= t.stops.length - 1
  if (atFinal) {
    completeTripAndGoLedger()
    return
  }
  if (isPickupStop(t) && !t.photoOk) {
    alert('도착지로 출발하기 전에 상차(적재) 사진을 등록해 주세요.')
    return
  }
  t.phase = 'EN_ROUTE'
  truckStatus.value = 'MOVING'
  truckStatusText.value = '운행 중'
  toast.value = `도착지로 출발 · ${nextStopName.value}`
  setTimeout(() => { toast.value = null }, 3000)
  addLogs(`출발지 ${currentStopName.value} → 도착지 ${nextStopName.value}`)
  saveActiveTrip()
}

function arriveAtStop() {
  const t = activeTrip.value
  if (!t || t.phase !== 'EN_ROUTE') return
  if (t.stopIndex >= t.stops.length - 1) {
    t.phase = 'DONE'
    truckStatus.value = 'IDLE'
    truckStatusText.value = '운행 완료'
    saveActiveTrip()
    return
  }
  const arrivedName = nextStopName.value
  t.stopIndex += 1
  t.phase = 'AT_STOP'
  t.photoOk = false
  truckStatus.value = 'LOADING'
  truckStatusText.value = t.stopIndex >= t.stops.length - 1 ? '최종 도착' : '상차 대기'
  toast.value = t.stopIndex >= t.stops.length - 1
    ? `최종 도착지 · ${arrivedName}`
    : `도착지에 도착 · ${arrivedName}`
  setTimeout(() => { toast.value = null }, 3000)
  addLogs(`도착지 도착: ${arrivedName}`)
  saveActiveTrip()
}

const mapLoaded = ref(false)
const mapMessage = ref('지도 준비 중...')
const mapHint = ref('')
const mapEl = ref(null)
const mapInstance = ref(null)
const polyline = ref(null)
const mapMarkers = ref([])

const odItemsModal = ref({
  show: false,
  loading: false,
  origin: '',
  destination: '',
  items: [],
  aggregateOnly: false,
})

const cargoPhotoModal = ref({
  show: false,
  url: '',
  title: '',
})

function cargoOptionLabel(item) {
  if (!item) return '-'
  if (item.productSummary) return item.productSummary
  if (item.productName) {
    const n = String(item.productName).replace('(그룹사진)', '').trim()
    return `${n} ${item.boxCount || 1}`
  }
  // 하위호환: 예전 데이터는 박스 표기
  return `${item.boxCount || '-'}박스`
}

function openCargoPhoto(item) {
  const url = item?.photoUrl
  if (!url) {
    alert('등록된 적재 사진이 없습니다.')
    return
  }
  cargoPhotoModal.value = {
    show: true,
    url,
    title: item.origin && item.destination
      ? `${item.origin} → ${item.destination}`
      : (item.productSummary || item.productName || ''),
  }
}

let feedTimer = null
let demoPollTimer = null
let lastDemoEpoch = null
let lastDemoResetAt = 0
let demoWipeBusy = false

function stationByCode(code) {
  return stations.value.find((s) => s.code === code)
}

function formatWon(n) {
  return Number(n || 0).toLocaleString('ko-KR') + '원'
}

function addLogs(items) {
  if (!items) return
  const list = Array.isArray(items) ? items : [items]
  logs.value.push(...list)
  nextTick(() => {
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  })
}

function startBusy(title, hint = 'AI 처리 중...') {
  stopBusyAnim()
  busy.value = { show: true, title, hint, percent: 8 }
  busyTimer = setInterval(() => {
    if (busy.value.percent < 90) busy.value.percent += Math.floor(3 + Math.random() * 8)
  }, 280)
}

function endBusy() {
  busy.value.percent = 100
  stopBusyAnim()
  setTimeout(() => { busy.value.show = false }, 280)
}

function stopBusyAnim() {
  if (busyTimer) { clearInterval(busyTimer); busyTimer = null }
}

function saveSession() {
  if (!me.value) return
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    truckId: me.value.truckId,
    phone: me.value.phone,
    truckNumber: me.value.truckNumber,
  }))
}

function clearSession() {
  sessionStorage.removeItem(SESSION_KEY)
}

function tripStorageKey(truckId) {
  return `${TRIP_KEY_PREFIX}${truckId}`
}

function saveActiveTrip() {
  const truckId = me.value?.truckId
  if (!truckId) return
  const t = activeTrip.value
  if (!t || t.phase === 'DONE') {
    try { localStorage.removeItem(tripStorageKey(truckId)) } catch (_) {}
    return
  }
  try {
    localStorage.setItem(tripStorageKey(truckId), JSON.stringify({
      trip: t,
      spaceMeasured: !!spaceMeasured.value,
      occupied: Number(occupied.value) || 0,
      remaining: Number(remaining.value) || 100,
      naviInfo: naviInfo.value,
      pendingDriveRoute: pendingDriveRoute.value,
      truckStatus: truckStatus.value,
      truckStatusText: truckStatusText.value,
      simKmAlong: simKmAlong.value,
      simPos: simPos.value,
      simAtEnd: !!simAtEnd.value,
      simAlertedCodes: simAlertedCodes.value,
      simAcceptedCodes: simAcceptedCodes.value,
      simRejectedCodes: simRejectedCodes.value,
      simOffer: simOffer.value,
      simNearby: simNearby.value,
    }))
  } catch (_) { /* quota */ }
}

function clearActiveTripStorage(truckId = me.value?.truckId) {
  if (!truckId) return
  try { localStorage.removeItem(tripStorageKey(truckId)) } catch (_) {}
}

function restoreActiveTrip(truckId) {
  if (!truckId) return false
  try {
    const raw = localStorage.getItem(tripStorageKey(truckId))
    if (!raw) return false
    const s = JSON.parse(raw)
    if (!s?.trip || s.trip.phase === 'DONE') {
      clearActiveTripStorage(truckId)
      return false
    }
    activeTrip.value = s.trip
    if (Array.isArray(s.trip.measuredLoads)) {
      s.trip.measuredLoads = cargoSegmentsForView(s.trip.measuredLoads)
    }
    spaceMeasured.value = !!s.spaceMeasured
    if (s.spaceMeasured) {
      occupied.value = Number(s.occupied) || 0
      remaining.value = Number(s.remaining ?? (100 - occupied.value))
    }
    if (s.naviInfo) naviInfo.value = s.naviInfo
    if (s.pendingDriveRoute) pendingDriveRoute.value = s.pendingDriveRoute
    simKmAlong.value = Number(s.simKmAlong) || 0
    simPos.value = s.simPos || null
    simAtEnd.value = !!s.simAtEnd
    simAlertedCodes.value = Array.isArray(s.simAlertedCodes) ? s.simAlertedCodes : []
    simAcceptedCodes.value = Array.isArray(s.simAcceptedCodes) ? s.simAcceptedCodes : []
    simRejectedCodes.value = Array.isArray(s.simRejectedCodes) ? s.simRejectedCodes : []
    simNearby.value = Array.isArray(s.simNearby) ? s.simNearby : []
    const restoredOffer = s.simOffer || null
    const remNow = (() => {
      const planned = Number((s.trip?.loads || []).reduce((sum, t) => sum + Number(t.fillPercent || 0), 0)) || 0
      let used = planned
      if (s.spaceMeasured) used = Math.max(used, Number(s.occupied) || 0)
      return Math.max(0, 100 - used)
    })()
    if (restoredOffer && Number(restoredOffer.fillPercent || 0) <= remNow + 0.01) {
      simOffer.value = restoredOffer
    } else {
      simOffer.value = null
    }
    truckStatus.value = s.truckStatus || (s.trip.phase === 'EN_ROUTE' ? 'MOVING' : 'LOADING')
    truckStatusText.value = s.truckStatusText
      || (s.trip.phase === 'EN_ROUTE' ? '운행 중' : '상차 대기')
    return true
  } catch (_) {
    clearActiveTripStorage(truckId)
    return false
  }
}

function isServerDemoCleared(data) {
  if (!data) return false
  const rem = Number(data.remainingVolumePercent ?? 100)
  const idle = String(data.status || 'IDLE').toUpperCase() === 'IDLE'
  const noJob = data.activeRequestId == null || data.activeRequestId === ''
  return idle && rem >= 99.5 && noJob
}

function clearAllActiveTripStorage() {
  try {
    const keys = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(TRIP_KEY_PREFIX)) keys.push(k)
    }
    keys.forEach((k) => localStorage.removeItem(k))
  } catch (_) { /* ignore */ }
}

function resetLocalTripState(reason = '') {
  activeTrip.value = null
  spaceMeasured.value = false
  occupied.value = 0
  remaining.value = 100
  occupancyGrid.value = null
  naviInfo.value = null
  pendingDriveRoute.value = null
  lastDrawnRoute = null
  resetSimProgress(true)
  dispatchCart.value = []
  cartPreview.value = null
  cartLastAddedKm.value = null
  cartDockOpen.value = false
  proposal.value = null
  optimalPlan.value = null
  guide.value = ''
  cargoItems.value = []
  ledger.value = null
  truckStatus.value = 'IDLE'
  truckStatusText.value = '대기 중'
  clearAllActiveTripStorage()
  clearCargoRouteDraw()
  if (polyline.value) {
    try { polyline.value.setMap(null) } catch (_) {}
    polyline.value = null
  }
  try { clearMarkers() } catch (_) {}
  if (tab.value === 'drive') tab.value = 'cargo'
  if (reason) addLogs(reason)
}

async function applyDemoWipe() {
  if (demoWipeBusy) return
  demoWipeBusy = true
  try {
    resetLocalTripState('시연 리셋 · 운행·장바구니 초기화')
    if (me.value?.truckId) {
      try {
        const { data } = await axios.get(`/api/drivers/${me.value.truckId}`)
        applyMe(data)
      } catch (_) { /* ignore */ }
    }
    try { await loadCargoTerminals() } catch (_) {}
    try { await refreshFeed() } catch (_) {}
    try { await loadLedger() } catch (_) {}
    toast.value = '시연이 초기화되었습니다'
    setTimeout(() => { toast.value = null }, 3500)
  } finally {
    demoWipeBusy = false
  }
}

async function syncDemoReset() {
  if (gate.value !== 'app' || !me.value?.truckId) return
  try {
    const { data } = await axios.get('/api/dispatch/demo-state', { timeout: 8000 })
    const epoch = Number(data.epoch || 0)
    if (lastDemoEpoch == null) {
      lastDemoEpoch = epoch
    } else if (epoch < lastDemoEpoch) {
      lastDemoEpoch = epoch
    } else if (epoch > lastDemoEpoch) {
      lastDemoEpoch = epoch
      try { localStorage.setItem(DEMO_EPOCH_KEY, String(epoch)) } catch (_) {}
      await applyDemoWipe()
      return
    }
  } catch (_) { /* 구버전 서버는 엔드포인트가 없을 수 있음 */ }
  // 배차 확정 전 장바구니/경로 미리보기는 서버가 IDLE이라서 시연 리셋으로 보면 안 됨.
  // 이미 확정된 운행만, 서버가 공차로 돌아갔을 때 보조 초기화.
  if (!activeTrip.value || activeTrip.value.phase === 'DONE') return
  try {
    const { data } = await axios.get(`/api/drivers/${me.value.truckId}`, { timeout: 8000 })
    if (isServerDemoCleared(data)) await applyDemoWipe()
  } catch (_) { /* ignore */ }
}

function onDemoResetStorage(e) {
  if (!e?.key) return
  if (e.key === DEMO_RESET_AT_KEY) {
    const ts = Number(e.newValue || 0)
    if (ts > lastDemoResetAt) {
      lastDemoResetAt = ts
      applyDemoWipe()
    }
    return
  }
  if (e.key === DEMO_EPOCH_KEY) {
    const epoch = Number(e.newValue || 0)
    if (epoch > lastDemoEpoch) {
      lastDemoEpoch = epoch
      applyDemoWipe()
    }
  }
}

function startDemoPolling() {
  stopDemoPolling()
  try { lastDemoResetAt = Number(localStorage.getItem(DEMO_RESET_AT_KEY) || 0) } catch (_) {}
  syncDemoReset()
  demoPollTimer = setInterval(syncDemoReset, 4000)
}

function stopDemoPolling() {
  if (demoPollTimer) {
    clearInterval(demoPollTimer)
    demoPollTimer = null
  }
}

function relayoutCargoMap() {
  try { cargoMapInstance.value?.relayout() } catch (_) {}
}

function applyMe(data) {
  me.value = data
  remaining.value = Number(data.remainingVolumePercent ?? 100)
  occupied.value = Number(data.occupiedVolumePercent ?? (100 - remaining.value))
  // 상차 사진 업로드로만 spaceMeasured=true (DB 잔여만으로 트럭 UI를 채우지 않음)
  const trip = activeTrip.value
  if (trip && trip.phase && trip.phase !== 'DONE') {
    truckStatus.value = trip.phase === 'EN_ROUTE' ? 'MOVING' : 'LOADING'
    truckStatusText.value = trip.phase === 'EN_ROUTE'
      ? '운행 중'
      : (trip.photoOk ? '상차 완료 · 출발 가능' : '상차 대기')
  } else {
    truckStatus.value = data.status || 'IDLE'
    truckStatusText.value = truckStatus.value === 'MOVING' ? '운행 중' : '대기 중'
  }
  if (data.originCode) routeForm.value.originCode = data.originCode
  if (data.destinationCode) routeForm.value.destinationCode = data.destinationCode
  saveSession()
}

function shortRouteLabel(label, max = 72) {
  const s = String(label || '')
  if (s.length <= max) return s
  return `${s.slice(0, max - 1)}…`
}

function resolveGate(data) {
  if (data.needProfile) gate.value = 'profile'
  else if (data.needRoute) {
    gate.value = 'route'
    loadTerminals({ force: true })
  } else {
    gate.value = 'app'
    nextTick(() => {
      if (tab.value === 'drive') mountDriveMap()
      if (tab.value === 'cargo') initCargoMap()
    })
  }
}

async function doLogin() {
  startBusy('기사 접속', '세션 확인 중...')
  try {
    const { data } = await axios.post('/api/drivers/login', {
      phone: loginForm.value.phone,
      truckNumber: loginForm.value.truckNumber,
      driverName: loginForm.value.driverName || undefined,
    })
    applyMe(data)
    profileForm.value.driverName = data.driverName || ''
    profileForm.value.capacityTons = data.capacityTons || 11
    profileForm.value.vehicleType = data.vehicleType || '윙바디'
    profileForm.value.remainingVolumePercent = data.remainingVolumePercent ?? 100
    if (isServerDemoCleared(data)) {
      clearAllActiveTripStorage()
    } else {
      restoreActiveTrip(data.truckId)
    }
    if (activeTrip.value && activeTrip.value.phase !== 'DONE') tab.value = 'drive'
    addLogs(data.message)
    resolveGate(data)
  } catch (e) {
    addLogs('로그인 실패: ' + (e.response?.data?.message || e.message))
    alert(e.response?.data?.message || e.message || '로그인 실패')
  } finally {
    endBusy()
  }
}

async function doProfile() {
  startBusy('차량 등록', '프로필 저장 중...')
  try {
    const { data } = await axios.post(`/api/drivers/${me.value.truckId}/profile`, profileForm.value)
    applyMe(data)
    addLogs(data.message)
    resolveGate(data)
  } catch (e) {
    alert(e.response?.data?.message || e.message)
  } finally {
    endBusy()
  }
}

async function doRoute() {
  startBusy('경로 설정', '출도착 저장 중...')
  try {
    const { data } = await axios.post(`/api/drivers/${me.value.truckId}/route`, routeForm.value)
    applyMe(data)
    addLogs(data.message)
    feedPage.value = 0
    resolveGate(data)
  } catch (e) {
    alert(e.response?.data?.message || e.message)
  } finally {
    endBusy()
  }
}

function logout() {
  stopFeedPolling()
  stopDemoPolling()
  lastDemoEpoch = null
  if (me.value?.truckId) clearActiveTripStorage(me.value.truckId)
  clearSession()
  me.value = null
  activeTrip.value = null
  spaceMeasured.value = false
  naviInfo.value = null
  pendingDriveRoute.value = null
  cargoItems.value = []
  proposal.value = null
  gate.value = 'login'
}

async function restoreSession() {
  const raw = sessionStorage.getItem(SESSION_KEY)
  if (!raw) return false
  try {
    const s = JSON.parse(raw)
    const { data } = await axios.get(`/api/drivers/${s.truckId}`)
    if (data.phone !== s.phone || data.truckNumber !== s.truckNumber) return false
    applyMe(data)
    const hadTrip = isServerDemoCleared(data)
      ? (clearAllActiveTripStorage(), false)
      : restoreActiveTrip(data.truckId)
    if (hadTrip) tab.value = 'drive'
    resolveGate(data)
    return true
  } catch (_) {
    clearSession()
    return false
  }
}

async function refreshFeed() {
  if (!me.value?.truckId || !selectedTerminal.value?.code) {
    cargoItems.value = []
    return
  }
  feedLoading.value = true
  try {
    const { data } = await axios.get('/api/dispatch/groups-by-terminal', {
      params: {
        truckId: me.value.truckId,
        terminalCode: selectedTerminal.value.code,
        page: feedPage.value,
      },
    })
    cargoItems.value = data.items || []
    feedHasMore.value = !!data.hasMore
    feedCandidateCount.value = Number(data.candidateCount || 0)
    // 장바구니 모드: 목록에서는 우회 API를 돌리지 않음 (담기 시 preview-cart로 계산)
  } catch (e) {
    addLogs('터미널 그룹 실패: ' + (e.message || e))
  } finally {
    feedLoading.value = false
  }
}

async function enrichVisibleDetours(items) {
  if (!me.value?.truckId || !items?.length) return
  await Promise.all(items.map(async (item) => {
    if (!item.odGroupId || item.extraDistanceKm != null) return
    item.detourLoading = true
    try {
      const { data } = await axios.get('/api/dispatch/estimate-detour', {
        params: { truckId: me.value.truckId, odGroupId: item.odGroupId },
        timeout: 60000,
      })
      item.extraDistanceKm = data.extraDistanceKm
      item.extraMinutes = data.extraMinutes
      item.extraFuelCost = data.extraFuelCost
      if (data.netProfit != null) item.netProfit = data.netProfit
      if (data.fillPercent != null) item.fillPercent = data.fillPercent
      item.distanceSource = data.distanceSource
    } catch (e) {
      addLogs(`우회 실패(#${item.odGroupId}): ` + (e.response?.data?.message || e.message || e))
    } finally {
      item.detourLoading = false
    }
  }))
}

async function nextFeedPage() {
  if (!feedHasMore.value) return
  feedPage.value += 1
  await refreshFeed()
}

async function prevFeedPage() {
  if (feedPage.value <= 0) return
  feedPage.value -= 1
  await refreshFeed()
}

function setDispatchMode(mode) {
  dispatchMode.value = mode
  optimalPlan.value = null
  if (mode === 'manual') {
    nextTick(() => initCargoMap())
  }
}

function clearTerminalSelection() {
  selectedTerminal.value = null
  cargoItems.value = []
  feedPage.value = 0
  highlightCargoTerminals({ fitBounds: false })
}

async function selectTerminalOnMap(t) {
  selectedTerminal.value = t
  feedPage.value = 0
  optimalPlan.value = null
  dispatchMode.value = 'manual'
  highlightCargoTerminals({ fitBounds: false })
  await refreshFeed()
}

async function loadCargoTerminals() {
  if (!me.value?.truckId) return
  try {
    const { data } = await axios.get('/api/dispatch/terminals-with-cargo', {
      params: { truckId: me.value.truckId },
    })
    const byCode = new Map()
    for (const t of (data.terminals || [])) {
      if (t.lat == null || t.lng == null || !t.code) continue
      if (!byCode.has(String(t.code))) byCode.set(String(t.code), t)
    }
    cargoTerminals.value = [...byCode.values()]
    if (!cargoTerminals.value.length) {
      cargoMapMessage.value = '물량 있는 터미널이 없습니다.'
    } else {
      cargoMapMessage.value = '터미널 코드를 선택하세요'
    }
    // 선택 터미널이 더 이상 PENDING 그룹이 없으면 시트 닫기
    if (selectedTerminal.value?.code) {
      const still = cargoTerminals.value.find((t) => String(t.code) === String(selectedTerminal.value.code))
      if (!still) {
        selectedTerminal.value = null
        cargoItems.value = []
      } else {
        selectedTerminal.value = { ...selectedTerminal.value, ...still }
      }
    }
    highlightCargoTerminals({ fitBounds: false })
  } catch (e) {
    addLogs('물량 터미널 로드 실패: ' + (e.message || e))
    cargoTerminals.value = []
  }
}

function clearCargoMapMarkers() {
  cargoMapMarkers.value.forEach((m) => { try { m.setMap(null) } catch (_) {} })
  cargoMapMarkers.value = []
}

/**
 * 지도 = 터미널 코드당 핀 1개.
 * 핀의 숫자는 그룹 개수(표시용). 클러스터러 사용 안 함.
 */
function highlightCargoTerminals({ fitBounds = false } = {}) {
  if (!cargoMapInstance.value || !window.kakao?.maps) return
  clearCargoMapMarkers()
  const bounds = new window.kakao.maps.LatLngBounds()

  cargoTerminals.value.forEach((t) => {
    if (t.lat == null || t.lng == null) return
    const pos = new window.kakao.maps.LatLng(Number(t.lat), Number(t.lng))
    bounds.extend(pos)
    const selected = selectedTerminal.value?.code === t.code
    const groups = t.groupCount != null ? t.groupCount : (t.waybillCount || 0)
    const bg = selected ? '#2f80ed' : '#fff'
    const fg = selected ? '#fff' : '#1a5bb8'
    const content = document.createElement('div')
    content.style.cssText = 'cursor:pointer;text-align:center;'
    content.innerHTML = `
      <div style="min-width:44px;padding:6px 8px;background:${bg};color:${fg};border:2px solid #2f80ed;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.18);">
        <div style="font-size:11px;font-weight:800;line-height:1.2;">${t.code}</div>
        <div style="font-size:10px;font-weight:700;opacity:.9;margin-top:2px;">그룹 ${groups}</div>
      </div>
    `
    content.addEventListener('click', (ev) => {
      ev.stopPropagation()
      selectTerminalOnMap(t)
    })
    const overlay = new window.kakao.maps.CustomOverlay({
      position: pos,
      content,
      yAnchor: 1.1,
      zIndex: selected ? 20 : 10,
      clickable: true,
    })
    overlay.setMap(cargoMapInstance.value)
    cargoMapMarkers.value.push(overlay)
  })

  if (fitBounds && !cargoMapFitted.value && !cartPreview.value) {
    try {
      if (!bounds.isEmpty()) {
        cargoMapInstance.value.setBounds(bounds)
        cargoMapFitted.value = true
      }
    } catch (_) { /* ignore */ }
  }
  // 장바구니 경로가 있으면 핀 갱신 후에도 다시 그림
  if (cartPreview.value) drawCartRouteOnCargoMap(cartPreview.value)
}

function initCargoMap() {
  if (tab.value !== 'cargo' || !cargoMapEl.value) return
  cargoMapMessage.value = '지도 로딩...'
  loadKakaoScript()
    .then(() => new Promise((resolve) => window.kakao.maps.load(() => resolve())))
    .then(async () => {
      await nextTick()
      if (!cargoMapEl.value || tab.value !== 'cargo') return
      await loadCargoTerminals()
      if (cargoMapInstance.value) {
        cargoMapLoaded.value = true
        highlightCargoTerminals({ fitBounds: false })
        try { cargoMapInstance.value.relayout() } catch (_) {}
        return
      }
      const o = cargoTerminals.value[0]
        || stationByCode(me.value?.originCode)
        || { lat: 35.1362, lng: 128.83 }
      cargoMapInstance.value = new window.kakao.maps.Map(cargoMapEl.value, {
        center: new window.kakao.maps.LatLng(o.lat || 35.1362, o.lng || 128.83),
        level: 9,
      })
      cargoMapLoaded.value = true
      cargoMapMessage.value = cargoTerminals.value.length
        ? '터미널 코드를 선택하세요'
        : '물량 터미널 없음'
      cargoMapFitted.value = false
      highlightCargoTerminals({ fitBounds: true })
      setTimeout(() => { try { cargoMapInstance.value.relayout() } catch (_) {} }, 100)
    })
    .catch((err) => {
      cargoMapMessage.value = '지도 실패: ' + (err.message || err)
    })
}

async function runOptimalPlan() {
  if (!me.value?.truckId) return
  startBusy('최적 배차', 'LLM이 수익·거리·시간을 계산 중...')
  try {
    const { data } = await axios.post('/api/dispatch/optimal-plan', { truckId: me.value.truckId })
    const recommended = sortItemsAlongDriver(data.recommended || [])
    optimalPlan.value = {
      ...data,
      recommended,
      requestIds: recommended.map((r) => r.requestId).filter(Boolean),
    }
    selectedTerminal.value = null
    cargoItems.value = []
    addLogs(data.briefing || '최적 배차 플랜 생성')
    if (data.summary?.routeHint) addLogs('경로: ' + data.summary.routeHint)
    toast.value = `추천 ${data.requestIds?.length || 0}건 · ${formatWon(data.summary?.totalNetProfit)}`
    setTimeout(() => { toast.value = null }, 4000)
  } catch (e) {
    addLogs('최적 배차 실패: ' + (e.message || e))
    alert(e.response?.data?.message || e.message || '최적 배차 실패')
  } finally {
    endBusy()
  }
}

/** LLM 추천 → 즉시 수락하지 않고 장바구니에 담기 (배차 확정은 장바구니에서) */
async function addOptimalPlanToCart() {
  const rawItems = optimalPlan.value?.recommended || []
  const items = sortItemsAlongDriver(rawItems)
  if (!items.length || !me.value?.truckId) {
    alert('담을 추천 화물이 없습니다')
    return
  }
  startBusy('장바구니', 'LLM 추천을 장바구니에 담는 중...')
  try {
    let added = 0
    let skipped = 0
    const rem = Number(me.value.remainingVolumePercent ?? remaining.value ?? 100)
    let used = dispatchCart.value.reduce((s, c) => s + Number(c.fillPercent || 0), 0)

    for (const item of items) {
      if (!item?.odGroupId && !item?.requestId) continue
      if (itemInCart(item)) {
        skipped += 1
        continue
      }
      const need = Number(item.fillPercent ?? item.fillPercentOf11t ?? 0)
      if (used + need > rem + 0.01) {
        addLogs(`공간 부족으로 스킵: ${item.origin} → ${item.destination} (${need}%)`)
        skipped += 1
        continue
      }
      dispatchCart.value.push({
        odGroupId: item.odGroupId,
        requestId: item.requestId,
        origin: item.origin,
        destination: item.destination,
        originCode: item.originCode,
        destinationCode: item.destinationCode,
        boxCount: item.boxCount,
        productSummary: item.productSummary,
        productName: item.productName,
        photoUrl: item.photoUrl,
        fillPercent: need,
        proposedFee: item.proposedFee || item.netProfit,
      })
      used += need
      added += 1
    }

    if (added > 0) {
      cartDockOpen.value = true
      await refreshCartPreview()
      await nextTick()
      relayoutCargoMap()
      setTimeout(() => {
        relayoutCargoMap()
        if (cartPreview.value) drawCartRouteOnCargoMap(cartPreview.value)
      }, 180)
    } else {
      cartDockOpen.value = true
    }
    optimalPlan.value = null
    toast.value = added
      ? `장바구니 +${added}건${skipped ? ` · 스킵 ${skipped}` : ''} · 배차 확정하세요`
      : (skipped ? '이미 담긴 화물이거나 공간 부족' : '담을 항목 없음')
    setTimeout(() => { toast.value = null }, 4000)
    addLogs(`LLM 추천 → 장바구니 ${added}건` + (skipped ? ` (스킵 ${skipped})` : ''))
  } catch (e) {
    addLogs('장바구니 담기 실패: ' + (e.message || e))
    alert(e.response?.data?.message || e.message || '장바구니 담기 실패')
  } finally {
    endBusy()
  }
}

/** @deprecated 하위 호환 — 장바구니 담기로 위임 */
async function acceptBatchPlan() {
  await addOptimalPlanToCart()
}

function startFeedPolling() {
  // 카카오 거리 호출이 있어 자동 폴링하지 않음 (터미널 선택/새로고침 시만)
  stopFeedPolling()
}

function stopFeedPolling() {
  if (feedTimer) { clearInterval(feedTimer); feedTimer = null }
}

function itemInCart(item) {
  return dispatchCart.value.some((c) => c.odGroupId === item.odGroupId || c.requestId === item.requestId)
}

function clearCargoRouteDraw() {
  if (cargoRouteLine) {
    try { cargoRouteLine.setMap(null) } catch (_) {}
    cargoRouteLine = null
  }
  cargoRouteMarkers.forEach((m) => { try { m.setMap(null) } catch (_) {} })
  cargoRouteMarkers = []
}

function isKoreaGps(lat, lng) {
  const a = Number(lat)
  const b = Number(lng)
  return Number.isFinite(a) && Number.isFinite(b)
    && a >= 33 && a <= 39.5 && b >= 124 && b <= 132.5
}

function downsamplePath(points, maxPts = 400) {
  if (!points?.length || points.length <= maxPts) return points || []
  const step = Math.ceil(points.length / maxPts)
  const out = []
  for (let i = 0; i < points.length; i += step) out.push(points[i])
  const last = points[points.length - 1]
  if (out[out.length - 1] !== last) out.push(last)
  return out
}

function haversineKm(a, b) {
  const R = 6371
  const dLat = ((Number(b.lat) - Number(a.lat)) * Math.PI) / 180
  const dLng = ((Number(b.lng) - Number(a.lng)) * Math.PI) / 180
  const x = Math.sin(dLat / 2) ** 2
    + Math.cos((Number(a.lat) * Math.PI) / 180)
    * Math.cos((Number(b.lat) * Math.PI) / 180)
    * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x))
}

function driveSimPath() {
  const raw = pendingDriveRoute.value?.path
  if (raw?.length >= 2) return raw.filter((p) => isKoreaGps(p.lat, p.lng))
  const drawn = lastDrawnRoute?.path
  if (drawn?.length >= 2) return drawn.filter((p) => isKoreaGps(p.lat, p.lng))
  const stops = (pendingDriveRoute.value?.stops || lastDrawnRoute?.stops || activeTrip.value?.stops || [])
    .filter((s) => isKoreaGps(s.lat, s.lng))
  return stops
}

function pointAlongPath(path, targetKm) {
  if (!path?.length) return null
  if (path.length === 1) {
    return { lat: Number(path[0].lat), lng: Number(path[0].lng), km: 0, atEnd: true }
  }
  let acc = 0
  for (let i = 0; i < path.length - 1; i++) {
    const a = { lat: Number(path[i].lat), lng: Number(path[i].lng) }
    const b = { lat: Number(path[i + 1].lat), lng: Number(path[i + 1].lng) }
    const seg = haversineKm(a, b)
    if (acc + seg >= targetKm) {
      const t = seg < 1e-6 ? 0 : (targetKm - acc) / seg
      return {
        lat: a.lat + (b.lat - a.lat) * t,
        lng: a.lng + (b.lng - a.lng) * t,
        km: targetKm,
        atEnd: false,
      }
    }
    acc += seg
  }
  const last = path[path.length - 1]
  return { lat: Number(last.lat), lng: Number(last.lng), km: acc, atEnd: true }
}

function resetSimProgress(clearOverlays) {
  simKmAlong.value = 0
  simPos.value = null
  simAtEnd.value = false
  simAlertedCodes.value = []
  simAcceptedCodes.value = []
  simRejectedCodes.value = []
  simOffer.value = null
  simNearby.value = []
  if (clearOverlays) clearSimOverlays()
}

function clearSimOverlays() {
  simOverlays.value.forEach((m) => { try { m.setMap(null) } catch (_) {} })
  simOverlays.value = []
}

function addSimOverlay(lat, lng, html, yAnchor = 1.2) {
  if (!mapInstance.value || !window.kakao?.maps) return
  const overlay = new window.kakao.maps.CustomOverlay({
    position: new window.kakao.maps.LatLng(Number(lat), Number(lng)),
    content: html,
    yAnchor,
    clickable: false,
  })
  overlay.setMap(mapInstance.value)
  simOverlays.value.push(overlay)
}

function placeSimOverlays() {
  clearSimOverlays()
  if (!mapInstance.value || !window.kakao?.maps) return
  const path = driveSimPath()
  let pos = simPos.value
  if (!pos && path.length) {
    pos = { lat: Number(path[0].lat), lng: Number(path[0].lng) }
  }
  if (pos && isKoreaGps(pos.lat, pos.lng)) {
    addSimOverlay(
      pos.lat,
      pos.lng,
      '<div class="sim-truck-pin" title="기사 위치">🚛</div>',
      0.5,
    )
  }
  for (const t of simNearby.value || []) {
    if (!isKoreaGps(t.lat, t.lng)) continue
    const fill = Number(t.fillPercent || 0).toFixed(1)
    const name = String(t.name || t.code || '터미널')
    addSimOverlay(
      t.lat,
      t.lng,
      `<div class="sim-opp-pin"><b>${name}</b><span>${fill}%</span></div>`,
      1.35,
    )
  }
}

function usableStopCode(code) {
  const s = String(code || '').trim()
  if (!s || s.startsWith('stop-') || s.startsWith('via-')) return ''
  return s
}

function tripDestCode() {
  const stops = activeTrip.value?.stops || []
  const destStop = [...stops].reverse().find((s) => String(s.role || '') === '도착')
    || (stops.length ? stops[stops.length - 1] : null)
  const candidates = [
    destStop?.code,
    destStop?.destinationCode,
    me.value?.destinationCode,
    routeForm.value?.destinationCode,
    cartPreview.value?.destinationCode,
  ]
  for (const c of candidates) {
    const s = usableStopCode(c)
    if (s) return s
  }
  return ''
}

function simRemainingPercent() {
  const planned = Number(plannedOccupied.value) || 0
  let used = Math.max(0, planned)
  if (spaceMeasured.value) {
    const meas = Number(occupied.value) || 0
    used = Math.max(used, meas)
  }
  return Math.round(Math.max(0, 100 - used) * 10) / 10
}

function offerFitsRemaining(offer, rem = simRemainingPercent()) {
  if (!offer) return false
  const need = Number(offer.fillPercent ?? offer.fillPercentOf11t ?? 0)
  return Number.isFinite(need) && need > 0 && need <= rem + 0.01
}

async function fetchNearbyLoadable(lat, lng) {
  if (!me.value?.truckId) return []
  const dest = tripDestCode()
  const rem = simRemainingPercent()
  if (rem < 0.5) {
    addLogs(`인근조회 스킵 · 계획 ${plannedOccupied.value}% 잔여 ${rem}% (여유 없음)`)
    return []
  }
  const { data } = await axios.get('/api/dispatch/nearby-loadable', {
    params: {
      truckId: me.value.truckId,
      lat,
      lng,
      radiusKm: SIM_RADIUS_KM,
      remainingPercent: rem,
      destinationCode: dest || undefined,
    },
  })
  const blocked = new Set([
    ...(simAcceptedCodes.value || []).map(String),
    ...(simRejectedCodes.value || []).map(String),
  ])
  const found = (Array.isArray(data?.terminals) ? data.terminals : [])
    .filter((t) => t.code && !blocked.has(String(t.code)))
    .filter((t) => offerFitsRemaining(t, rem))
  const labels = found.map((t) => `${t.code || t.name} ${Number(t.fillPercent || 0).toFixed(1)}%`).join(', ')
  addLogs(`인근조회 dest=${dest || data?.destinationCode || '-'} 계획=${plannedOccupied.value}% 잔여=${rem}% → ${found.length}곳`
    + (labels ? ` (${labels})` : ''))
  return found
}

let simOfferBootstrapping = false
async function bootstrapSimOffer() {
  if (simOfferBootstrapping || !me.value?.truckId) return
  const path = driveSimPath()
  let lat
  let lng
  if (simPos.value && isKoreaGps(simPos.value.lat, simPos.value.lng)) {
    lat = Number(simPos.value.lat)
    lng = Number(simPos.value.lng)
  } else if (path.length) {
    lat = Number(path[0].lat)
    lng = Number(path[0].lng)
  } else {
    return
  }
  if (!isKoreaGps(lat, lng)) return
  simOfferBootstrapping = true
  try {
    await refreshSimOfferAt(lat, lng)
    placeSimOverlays()
    saveActiveTrip()
  } catch (e) {
    addLogs('인근 물량 조회 실패: ' + (e.message || e))
  } finally {
    simOfferBootstrapping = false
  }
}

async function stepDriverAlongRoute() {
  const path = driveSimPath()
  if (path.length < 2) {
    toast.value = '내비 경로가 없습니다'
    setTimeout(() => { toast.value = null }, 2500)
    return
  }
  if (simAtEnd.value) {
    toast.value = '도착지 부근입니다'
    setTimeout(() => { toast.value = null }, 3000)
    return
  }
  const nextKm = (Number(simKmAlong.value) || 0) + SIM_STEP_KM
  const pt = pointAlongPath(path, nextKm)
  if (!pt) return
  simKmAlong.value = pt.km
  simPos.value = { lat: pt.lat, lng: pt.lng }
  simAtEnd.value = !!pt.atEnd
  if (mapInstance.value && window.kakao?.maps) {
    try {
      mapInstance.value.panTo(new window.kakao.maps.LatLng(pt.lat, pt.lng))
    } catch (_) { /* ignore */ }
  }
  try {
    await refreshSimOfferAt(pt.lat, pt.lng)
  } catch (e) {
    addLogs('인근 물량 조회 실패: ' + (e.message || e))
  }
  if (pt.atEnd && !simOffer.value) {
    toast.value = '도착지 부근입니다'
    setTimeout(() => { toast.value = null }, 3000)
  }
  placeSimOverlays()
  saveActiveTrip()
}

function syncSimOfferWithFound(found) {
  const rem = simRemainingPercent()
  const blocked = new Set([
    ...(simAcceptedCodes.value || []).map(String),
    ...(simRejectedCodes.value || []).map(String),
  ])
  const inRange = (found || []).filter((t) =>
    t.code && !blocked.has(String(t.code)) && offerFitsRemaining(t, rem))
  const cur = simOffer.value
  if (cur && (!offerFitsRemaining(cur, rem) || blocked.has(String(cur.code))
    || !inRange.some((t) => String(t.code) === String(cur.code)))) {
    simOffer.value = null
  }
  if (!simOffer.value && inRange.length) {
    simOffer.value = inRange[0]
  }
}

function rejectSimOffer() {
  const offer = simOffer.value
  if (!offer) return
  const code = String(offer.code || offer.originCode || '')
  if (code) {
    simRejectedCodes.value = [...new Set([...(simRejectedCodes.value || []), code])]
  }
  addLogs(`인근 복화 거절: ${offer.name || offer.code || code}`)
  simOffer.value = null
  simNearby.value = (simNearby.value || []).filter((t) => String(t.code) !== code)
  placeSimOverlays()
  saveActiveTrip()
}

async function refreshSimOfferAt(lat, lng) {
  const found = await fetchNearbyLoadable(lat, lng)
  simNearby.value = found
  syncSimOfferWithFound(found)
}

function insertAcceptedStopIntoTrip(offer) {
  const t = activeTrip.value
  if (!t || !Array.isArray(t.stops) || !t.stops.length) return false
  const code = String(offer.originCode || offer.code || '').trim()
  const name = offer.origin || offer.name || code || '경유'
  if (!Array.isArray(t.loads)) t.loads = []
  const fill = Number(offer.fillPercent || 0)
  const loadHit = t.loads.find((l) => code && String(l.code) === code)
  if (loadHit) {
    loadHit.fillPercent = Math.round((Number(loadHit.fillPercent || 0) + fill) * 100) / 100
    t.loads = t.loads.map((x) => (x === loadHit ? { ...loadHit } : x))
  } else {
    t.loads = [...t.loads, {
      code: code || `stop-${t.loads.length}`,
      name,
      fillPercent: fill,
      color: TERM_COLORS[t.loads.length % TERM_COLORS.length],
      odGroupId: offer.odGroupId,
    }]
  }
  const existIdx = t.stops.findIndex((s) =>
    (code && String(s.code) === code) || (name && String(s.name) === name))
  if (existIdx >= 0) {
    activeTrip.value = { ...t, loads: t.loads, stops: t.stops.slice() }
    return existIdx > Number(t.stopIndex)
  }
  // 지금 출→도착 구간은 유지하고, 최종 도착 바로 앞에 경유를 붙인다.
  const destIdx = Math.max(t.stops.length - 1, 1)
  const insertAt = destIdx
  t.stops.splice(insertAt, 0, {
    code: code || `via-${insertAt}`,
    name,
    role: '경유',
    lat: offer.lat,
    lng: offer.lng,
  })
  if (Array.isArray(t.measuredLoads)) {
    t.measuredLoads.forEach((m) => {
      if (Number(m.stopIndex) >= insertAt) m.stopIndex = Number(m.stopIndex) + 1
    })
  }
  activeTrip.value = { ...t, loads: t.loads, stops: t.stops.slice(), measuredLoads: t.measuredLoads }
  if (pendingDriveRoute.value?.stops) {
    pendingDriveRoute.value.stops = t.stops.map((s) => ({ ...s }))
  }
  return true
}

async function restitchTripRoute() {
  const t = activeTrip.value
  const stops = (t?.stops || []).filter((s) => isKoreaGps(s.lat, s.lng))
  if (stops.length < 2) return
  try {
    const { data } = await axios.post('/api/dispatch/restitch-route', { stops }, { timeout: 90000 })
    const path = (data.path || []).filter((p) => isKoreaGps(p.lat, p.lng))
    if (path.length >= 2) {
      pendingDriveRoute.value = {
        path,
        stops: t.stops.map((s) => ({ ...s })),
      }
      lastDrawnRoute = { path, stops: pendingDriveRoute.value.stops }
      if (naviInfo.value) {
        naviInfo.value = {
          ...naviInfo.value,
          distance: data.totalKm ?? naviInfo.value.distance,
          durationMin: data.durationMin ?? naviInfo.value.durationMin,
          route: t.stops.map((s) => s.name).filter(Boolean).join(' → '),
        }
      }
    } else if (pendingDriveRoute.value) {
      pendingDriveRoute.value.stops = t.stops.map((s) => ({ ...s }))
    }
  } catch (e) {
    addLogs('경로 재계산 스킵: ' + (e.message || e))
    if (pendingDriveRoute.value) {
      pendingDriveRoute.value.stops = t.stops.map((s) => ({ ...s }))
    }
  }
}

async function acceptSimOffer() {
  const offer = simOffer.value
  if (!offer?.requestId || !me.value?.truckId) {
    toast.value = '수락할 물량 정보가 없습니다'
    setTimeout(() => { toast.value = null }, 2500)
    return
  }
  const rem = simRemainingPercent()
  const need = Number(offer.fillPercent || 0)
  if (need > rem + 0.01) {
    alert(`계획 잔여 ${rem.toFixed(1)}%로는 ${need.toFixed(1)}% 물량을 실을 수 없습니다.`)
    simOffer.value = null
    return
  }
  startBusy('복화 수락', '물량을 배정하는 중...')
  try {
    const { data } = await axios.post(`/api/dispatch/${offer.requestId}/accept`, {
      truckId: me.value.truckId,
      skipOdAdvance: true,
      remainingPercent: rem,
      fillPercent: need,
    })
    if (data.status === 'ALREADY_ASSIGNED') {
      alert('이미 배차되었습니다.')
      simOffer.value = null
      return
    }
    if (data.status === 'INSUFFICIENT_SPACE') {
      alert(data.message || '잔여공간이 부족합니다')
      return
    }
    const code = String(offer.code || '')
    if (code) simAcceptedCodes.value = [...new Set([...(simAcceptedCodes.value || []), code])]
    const inserted = insertAcceptedStopIntoTrip(offer)
    simOffer.value = null
    addLogs(`인근 복화 수락: ${offer.name || offer.code} ${need.toFixed(1)}%`
      + (inserted ? ' · 도착 앞 경유' : '')
      + ` · 계획 ${plannedOccupied.value}% 잔여 ${simRemainingPercent()}%`)
    toast.value = inserted
      ? `${offer.name || offer.code} 수락 · 도착 전 경유 추가`
      : `${offer.name || offer.code} 물량 수락`
    setTimeout(() => { toast.value = null }, 3000)
    const st = await axios.get(`/api/drivers/${me.value.truckId}`)
    applyMe(st.data)
    await restitchTripRoute()
    const pos = simPos.value
    if (pos && isKoreaGps(pos.lat, pos.lng)) {
      try { await refreshSimOfferAt(pos.lat, pos.lng) } catch (_) { /* ignore */ }
    }
    saveActiveTrip()
    if (tab.value === 'drive') {
      await nextTick()
      redrawLastDriveRoute()
      placeSimOverlays()
    }
  } catch (e) {
    addLogs('인근 물량 수락 실패: ' + (e.message || e))
    alert(e.response?.data?.message || e.message || '수락 실패')
  } finally {
    endBusy()
  }
}

function drawCartRouteOnCargoMap(preview) {
  if (!cargoMapInstance.value || !window.kakao?.maps) {
    clearCargoRouteDraw()
    return
  }
  clearCargoRouteDraw()
  const src = String(preview?.pathSource || '')
  const rawPath = (preview?.path || [])
    .filter((p) => isKoreaGps(p.lat, p.lng))
  const stopsOk = (preview?.stops || []).filter((s) => isKoreaGps(s.lat, s.lng))
  // 직선(stops-only)은 내비 경로로 그리지 않음 — 마커만
  const isStraight = src.includes('stops') || src.includes('fallback') || rawPath.length < 8
  let pts = isStraight ? [] : downsamplePath(rawPath)
  if (pts.length < 2 && !isStraight && stopsOk.length >= 2) {
    pts = []
  }
  const bounds = new window.kakao.maps.LatLngBounds()
  if (pts.length >= 2) {
    const path = pts.map((p) => new window.kakao.maps.LatLng(Number(p.lat), Number(p.lng)))
    cargoRouteLine = new window.kakao.maps.Polyline({
      path,
      strokeWeight: 5,
      strokeColor: '#2f80ed',
      strokeOpacity: 0.9,
      strokeStyle: 'solid',
    })
    cargoRouteLine.setMap(cargoMapInstance.value)
    path.forEach((p) => bounds.extend(p))
  }
  stopsOk.forEach((s, i) => {
    const pos = new window.kakao.maps.LatLng(Number(s.lat), Number(s.lng))
    bounds.extend(pos)
    const label = document.createElement('div')
    label.style.cssText = 'padding:3px 7px;background:#fff;border:1px solid #2f80ed;border-radius:6px;font-size:10px;font-weight:800;pointer-events:none;white-space:nowrap;'
    label.textContent = `${i + 1}. ${s.name || s.code}`
    const ov = new window.kakao.maps.CustomOverlay({
      position: pos,
      content: label,
      yAnchor: 1.4,
      clickable: false,
    })
    ov.setMap(cargoMapInstance.value)
    cargoRouteMarkers.push(ov)
  })
  try {
    if (stopsOk.length || pts.length >= 2) cargoMapInstance.value.setBounds(bounds)
  } catch (_) {}
  relayoutCargoMap()
  setTimeout(() => {
    relayoutCargoMap()
    try { cargoMapInstance.value?.setBounds(bounds) } catch (_) {}
  }, 120)
}

async function refreshCartPreview() {
  if (!me.value?.truckId) return
  if (!dispatchCart.value.length) {
    cartPreview.value = null
    cartLastAddedKm.value = null
    clearCargoRouteDraw()
    highlightCargoTerminals({ fitBounds: false })
    return
  }
  try {
    const { data } = await axios.post('/api/dispatch/preview-cart', {
      truckId: me.value.truckId,
      odGroupIds: dispatchCart.value.map((c) => c.odGroupId),
    }, { timeout: 120000 })
    cartPreview.value = data
    if (data.pathSource === 'stops-only' || !(data.path?.length >= 8)) {
      addLogs(`장바구니 경로: 도로 vertex 부족 (${data.pathSource || '?'} · ${(data.path || []).length}pts) — 스티치 재시도`)
    } else {
      addLogs(`장바구니 도로경로: ${data.pathSource} · ${(data.path || []).length}pts · ${data.totalKm}km`)
    }
    // 서버가 진행 방향 순으로 돌려준 items 순서로 장바구니 재정렬
    const byId = new Map((data.items || []).map((r) => [r.odGroupId, r]))
    const ordered = (data.items || [])
      .map((r) => {
        const c = dispatchCart.value.find((x) => x.odGroupId === r.odGroupId)
        return c ? { ...c, addedKm: r.addedKm, totalKmAfter: r.totalKmAfter } : null
      })
      .filter(Boolean)
    const rest = dispatchCart.value.filter((c) => !byId.has(c.odGroupId))
    dispatchCart.value = ordered.length ? [...ordered, ...rest] : dispatchCart.value.map((c) => {
      const row = byId.get(c.odGroupId)
      return row ? { ...c, addedKm: row.addedKm, totalKmAfter: row.totalKmAfter } : c
    })
    const last = data.items?.[data.items.length - 1]
    cartLastAddedKm.value = last?.addedKm ?? null
    await nextTick()
    if (!cargoMapInstance.value) await initCargoMap()
    drawCartRouteOnCargoMap(data)
    pendingDriveRoute.value = {
      path: (data.path || []).filter((p) => isKoreaGps(p.lat, p.lng)).map((p) => ({ lat: p.lat, lng: p.lng })),
      stops: (data.stops || []).filter((s) => isKoreaGps(s.lat, s.lng)),
    }
    setTimeout(() => {
      relayoutCargoMap()
      if (cartPreview.value) drawCartRouteOnCargoMap(cartPreview.value)
    }, 160)
  } catch (e) {
    addLogs('장바구니 경로 미리보기 실패: ' + (e.message || e))
  }
}

async function addToDispatchCart(item) {
  if (!item?.odGroupId || !me.value?.truckId) return
  if (itemInCart(item)) {
    toast.value = '이미 장바구니에 있습니다'
    setTimeout(() => { toast.value = null }, 2500)
    return
  }
  const rem = Number(me.value.remainingVolumePercent ?? remaining.value ?? 100)
  const need = Number(item.fillPercent ?? item.fillPercentOf11t ?? 0)
  const used = dispatchCart.value.reduce((s, c) => s + Number(c.fillPercent || 0), 0)
  if (used + need > rem + 0.01) {
    alert(`잔여공간 부족 (잔여 ${rem.toFixed(1)}% · 담기 ${need}% · 장바구니 ${used.toFixed(1)}%)`)
    return
  }
  dispatchCart.value.push({
    odGroupId: item.odGroupId,
    requestId: item.requestId,
    origin: item.origin,
    destination: item.destination,
    originCode: item.originCode,
    destinationCode: item.destinationCode,
    boxCount: item.boxCount,
    productSummary: item.productSummary,
    productName: item.productName,
    photoUrl: item.photoUrl,
    fillPercent: need,
    proposedFee: item.proposedFee || item.netProfit,
  })
  startBusy('경로 갱신', '장바구니 경로·증분 거리 계산 중...')
  try {
    await refreshCartPreview()
    const added = cartLastAddedKm.value
    toast.value = added != null && added > 0
      ? `담기 완료 · 경로 +${added}km`
      : `담기 완료 · ${item.origin} → ${item.destination}`
    setTimeout(() => { toast.value = null }, 3500)
    addLogs(`장바구니 +1: ${item.origin} → ${item.destination}`
      + (added != null ? ` (+${added}km)` : ''))
  } finally {
    endBusy()
  }
}

async function removeFromCart(odGroupId) {
  dispatchCart.value = dispatchCart.value.filter((c) => c.odGroupId !== odGroupId)
  await refreshCartPreview()
}

async function clearDispatchCart() {
  dispatchCart.value = []
  cartPreview.value = null
  cartLastAddedKm.value = null
  clearCargoRouteDraw()
  highlightCargoTerminals({ fitBounds: false })
}

async function confirmDispatchCart() {
  if (!dispatchCart.value.length || !me.value?.truckId) return
  const ids = (cartPreview.value?.requestIds?.length
    ? cartPreview.value.requestIds
    : dispatchCart.value.map((c) => c.requestId)).filter(Boolean)
  if (!ids.length) {
    alert('배정할 요청이 없습니다')
    return
  }
  startBusy('배차 확정', '장바구니 복화를 배정 중...')
  try {
    const { data } = await axios.post('/api/dispatch/accept-batch', {
      truckId: me.value.truckId,
      requestIds: ids,
    })
    addLogs(data.message || `장바구니 ${ids.length}건 배정`)
    // 도로 vertex가 충분한 미리보기 경로 확보 (직선 폴백이면 서버 재계산)
    let preview = cartPreview.value
    if (!preview?.path || preview.path.length < 20) {
      try {
        const { data: again } = await axios.post('/api/dispatch/preview-cart', {
          truckId: me.value.truckId,
          odGroupIds: dispatchCart.value.map((c) => c.odGroupId).filter(Boolean),
        }, { timeout: 90000 })
        preview = again
        cartPreview.value = again
      } catch (_) { /* 기존 preview 유지 */ }
    }
    const path = (preview?.path?.length
      ? preview.path
      : (data.path || [])).map((p) => ({ lat: p.lat, lng: p.lng }))
    const stops = preview?.stops?.length
      ? preview.stops
      : (data.stops || [])
    if (preview) {
      const base = Number(preview.baseKm) || 0
      const total = Number(preview.totalKm) || 0
      const extra = Number(preview.extraKm) || 0
      naviInfo.value = {
        distance: total,
        duration: preview.durationMin ?? preview.extraMinutes,
        durationMin: preview.durationMin ?? preview.extraMinutes,
        extraMinutes: preview.durationMin != null ? preview.extraMinutes : 0,
        extraKm: extra,
        nextStep: base > 0 && extra > 0.5
          ? `직행 ${base}km 대비 +${extra}km`
          : (total > 0 ? `총 주행 ${total}km` : '배차 확정'),
        route: preview.routeLabel,
      }
    }
    const cartSnapshot = sortItemsAlongDriver([...dispatchCart.value])
    startActiveTrip({ stops, cartItems: cartSnapshot })
    await clearDispatchCart()
    const safePath = (path || []).filter((p) => isKoreaGps(p.lat, p.lng))
    const safeStops = (stops || []).filter((s) => isKoreaGps(s.lat, s.lng))
    pendingDriveRoute.value = (safePath.length || safeStops.length)
      ? { path: safePath, stops: safeStops }
      : null
    saveActiveTrip()
    tab.value = 'drive'
    const st = await axios.get(`/api/drivers/${me.value.truckId}`)
    applyMe(st.data)
    await loadCargoTerminals()
    await refreshFeed()
    await loadLedger()
    toast.value = data.message || '배차 확정'
    setTimeout(() => { toast.value = null }, 4000)
  } catch (e) {
    addLogs('장바구니 확정 실패: ' + (e.message || e))
    alert(e.response?.data?.message || e.message)
  } finally {
    endBusy()
    if (tab.value === 'drive') {
      await nextTick()
      await mountDriveMap({ remount: true })
    }
  }
}

function selectCargo(item) {
  proposal.value = item
  tab.value = 'drive'
}

async function acceptFromList(item) {
  // 하위 호환: 즉시 수락 대신 장바구니에 담기
  await addToDispatchCart(item)
}

async function acceptProposal(opts = {}) {
  const stayOnCargo = !!opts.stayOnCargo
  if (!proposal.value?.requestId || !me.value?.truckId) return
  startBusy('배차 수락', '경로·정산 계산 중...')
  try {
    const { data } = await axios.post(`/api/dispatch/${proposal.value.requestId}/accept`, {
      truckId: me.value.truckId,
      skipOdAdvance: true,
    })
    if (data.status === 'ALREADY_ASSIGNED') {
      addLogs(`이미 배차되었습니다.${data.assignedDriverName ? ' (' + data.assignedDriverName + ')' : ''}`)
      alert('이미 배차되었습니다.')
      proposal.value = null
      await loadCargoTerminals()
      await refreshFeed()
      return
    }
    if (data.status === 'INSUFFICIENT_SPACE') {
      alert(data.message)
      return
    }
    addLogs(data.message)
    if (data.odAdvance?.message) addLogs('다음 OD: ' + data.odAdvance.message)
    const routeNames = data.naviRoute || []
    naviInfo.value = {
      distance: data.distanceKm ?? '-',
      duration: data.durationMin ?? '-',
      durationMin: data.durationMin,
      extraMinutes: data.extraMinutes ?? 0,
      nextStep: data.nextStep || '',
      route: Array.isArray(routeNames) ? routeNames.join(' → ') : '',
    }
    const path = (data.path || []).filter((p) => isKoreaGps(p.lat, p.lng)).map((p) => ({ lat: p.lat, lng: p.lng }))
    const stops = (data.stops || []).filter((s) => isKoreaGps(s.lat, s.lng)).map((s) => ({ ...s }))
    if (path.length || stops.length) {
      pendingDriveRoute.value = { path, stops }
    }
    startActiveTrip({
      stops,
      proposalItem: proposal.value
        ? {
            origin: proposal.value.origin,
            originCode: proposal.value.originCode,
            fillPercent: proposal.value.fillPercent ?? proposal.value.fillPercentOf11t,
            photoUrl: proposal.value.photoUrl,
          }
        : null,
    })
    const extra = proposal.value.extraDistanceKm
    toast.value = extra != null
      ? `수락 완료 · 우회 +${extra}km`
      : (data.message || '수락 완료')
    setTimeout(() => { toast.value = null }, 4000)
    proposal.value = null
    if (!stayOnCargo) tab.value = 'drive'
    const st = await axios.get(`/api/drivers/${me.value.truckId}`)
    applyMe(st.data)
    await loadCargoTerminals()
    await refreshFeed()
    await loadLedger()
  } catch (e) {
    addLogs('수락 실패: ' + (e.message || e))
  } finally {
    endBusy()
    if (!stayOnCargo && tab.value === 'drive') {
      await nextTick()
      await mountDriveMap({ remount: true })
    }
  }
}

function dismissProposal() {
  if (proposal.value?.requestId) dismissed.value.add(proposal.value.requestId)
  proposal.value = null
}

async function loadLedger() {
  if (!me.value?.truckId) return
  const { data } = await axios.get('/api/dispatch/ledger', { params: { truckId: me.value.truckId } })
  ledger.value = data
}

function openAdminVolume() {
  window.location.href = '/admin/'
}

async function loadTerminals(opts = {}) {
  const force = !!opts.force
  if (terminalsLoading.value) return
  if (!force && stations.value.length) return
  terminalsLoading.value = true
  const fallback = [
    { code: '200', name: '부산강서터미널', lat: 35.1362, lng: 128.83 },
    { code: '201', name: '부산사상터미널', lat: 35.1526, lng: 128.991 },
    { code: '300', name: '대구북구터미널', lat: 35.8858, lng: 128.5828 },
    { code: '308', name: '김천터미널', lat: 36.1398, lng: 128.1136 },
    { code: '500', name: '대전대덕터미널', lat: 36.4194, lng: 127.431 },
    { code: '501', name: '대전유성터미널', lat: 36.4102, lng: 127.3894 },
    { code: '503', name: '천안터미널', lat: 36.8151, lng: 127.1139 },
    { code: '514', name: '진천터미널', lat: 36.8555, lng: 127.4356 },
    { code: '001', name: '서울동부터미널', lat: 37.5745, lng: 127.0555 },
    { code: '008', name: '서울강남터미널', lat: 37.5172, lng: 127.0473 },
  ]
  let lastErr = null
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const { data } = await axios.get('/api/dispatch/terminals', { timeout: 15000 })
      const list = data.terminals || data.stations || []
      if (list.length) {
        stations.value = list
        if (!routeForm.value.originCode) routeForm.value.originCode = '200'
        if (!routeForm.value.destinationCode) routeForm.value.destinationCode = '001'
        terminalsLoading.value = false
        return
      }
    } catch (e) {
      lastErr = e
      try {
        const { data } = await axios.get('/api/dispatch/stations', { timeout: 15000 })
        const list = data.stations || data.terminals || []
        if (list.length) {
          stations.value = list
          if (!routeForm.value.originCode) routeForm.value.originCode = '200'
          if (!routeForm.value.destinationCode) routeForm.value.destinationCode = '001'
          terminalsLoading.value = false
          return
        }
      } catch (e2) {
        lastErr = e2
      }
    }
    await new Promise((r) => setTimeout(r, 700 * (attempt + 1)))
  }
  stations.value = fallback
  if (!routeForm.value.originCode) routeForm.value.originCode = '200'
  if (!routeForm.value.destinationCode) routeForm.value.destinationCode = '001'
  if (lastErr) addLogs('터미널 API 실패 → 시연 목록 사용: ' + (lastErr.message || lastErr))
  terminalsLoading.value = false
}

async function openOdItems(item) {
  if (!item?.odGroupId) {
    alert('이 항목에는 OD 그룹이 없습니다.')
    return
  }
  odItemsModal.value = {
    show: true,
    loading: true,
    origin: item.origin,
    destination: item.destination,
    items: [],
    aggregateOnly: false,
  }
  try {
    const { data } = await axios.get(`/api/dispatch/od-groups/${item.odGroupId}/items`, {
      params: { limit: 500 },
    })
    odItemsModal.value.items = data.items || []
    odItemsModal.value.aggregateOnly = !!data.aggregateOnly
    odItemsModal.value.origin = data.origin || item.origin
    odItemsModal.value.destination = data.destination || item.destination
  } catch (e) {
    addLogs('목록 실패: ' + (e.message || e))
    alert('목록을 불러오지 못했습니다.')
    odItemsModal.value.show = false
  } finally {
    odItemsModal.value.loading = false
  }
}

async function clearTruckSpace() {
  if (!me.value?.truckId) return
  if (!confirm('적재를 비우고 잔여공간을 100%로 되돌릴까요? (정산 이력은 유지됩니다)')) return
  startBusy('적재 비우기', '잔여공간을 100%로 초기화 중...')
  try {
    const { data } = await axios.post('/api/dispatch/truck/clear-space', null, {
      params: { truckId: me.value.truckId },
    })
    remaining.value = Number(data.remainingVolumePercent ?? 100)
    occupied.value = Number(data.occupiedVolumePercent ?? 0)
    spaceMeasured.value = false
    occupancyGrid.value = null
    if (activeTrip.value) activeTrip.value.measuredLoads = []
    guide.value = data.message || '적재를 비웠습니다.'
    truckStatus.value = 'IDLE'
    truckStatusText.value = '대기 중'
    applyMe({ ...me.value, ...data, remainingVolumePercent: remaining.value })
    saveActiveTrip()
    addLogs(data.message || '잔여 100%로 비움')
    toast.value = '잔여 100% · 적재 비움'
    setTimeout(() => { toast.value = null }, 3000)
  } catch (e) {
    addLogs('적재 비우기 실패: ' + (e.message || e))
    alert(e.response?.data?.message || e.message || '적재 비우기 실패')
  } finally {
    endBusy()
  }
}

async function onImageUpload(e) {
  const file = e.target.files?.[0]
  if (!file || !me.value) return
  showLogs.value = true
  addLogs([
    `사진 업로드: ${file.name}`,
    'RFP 3단 파이프라인 요청 → [1/3] Depth Anything · [2/3] YOLOv8-Seg · [3/3] py3dbp',
  ])
  startBusy('잔여공간 3단 실측', '[1/3] Depth → [2/3] Seg → [3/3] Pack')
  const form = new FormData()
  form.append('file', file)
  form.append('truckId', String(me.value.truckId))
  try {
    const { data } = await axios.post('/api/load/upload', form, { timeout: 180000 })
    occupied.value = Number(data.occupiedVolumePercent ?? 0)
    remaining.value = Number(data.remainingVolumePercent ?? 100)
    spaceMeasured.value = true
    occupancyGrid.value = data.occupancyGrid || data.occupancy_grid || null
    guide.value = data.guide
    if (activeTrip.value && activeTrip.value.phase === 'AT_STOP') {
      recordMeasuredLoadAtStop(occupied.value)
      activeTrip.value.photoOk = true
      truckStatus.value = 'LOADING'
      truckStatusText.value = '상차 완료 · 출발 가능'
    } else {
      truckStatus.value = 'LOADING'
      truckStatusText.value = '상차 중'
    }
    saveActiveTrip()
    addLogs(data.logs)
    if (data.pipeline) addLogs('사용 파이프라인: ' + (Array.isArray(data.pipeline) ? data.pipeline.join(' → ') : data.pipeline))
    if (data.engine) addLogs('엔진: ' + data.engine)
    const segs = activeTrip.value?.measuredLoads || []
    addLogs(
      `실측 적재 갱신: ${occupied.value}% (${loadedCbm.value} m³ / ${truckCapacityM3.value} m³)`
      + (segs.length ? ` · 세그먼트 ${segs.map((s) => `${s.name}:${s.fillPercent}%`).join(' + ')}` : ''),
    )
  } catch (err) {
    addLogs('이미지 분석 실패: ' + (err.message || err))
  } finally {
    endBusy()
    e.target.value = ''
  }
}

function clearMarkers() {
  mapMarkers.value.forEach((m) => { try { m.setMap(null) } catch (_) {} })
  mapMarkers.value = []
}

function addMarker(lat, lng, title) {
  if (!mapInstance.value || !window.kakao?.maps) return
  const marker = new window.kakao.maps.Marker({
    position: new window.kakao.maps.LatLng(lat, lng),
    map: mapInstance.value,
    title: title || '',
  })
  mapMarkers.value.push(marker)
}

function addStationLabel(lat, lng, text) {
  if (!mapInstance.value || !window.kakao?.maps) return
  const content = `<div style="padding:4px 8px;background:#fff;border:1px solid #2f80ed;border-radius:6px;font-size:11px;font-weight:700;white-space:nowrap;pointer-events:none;">${text}</div>`
  const overlay = new window.kakao.maps.CustomOverlay({
    position: new window.kakao.maps.LatLng(lat, lng),
    content,
    yAnchor: 2.2,
    clickable: false,
  })
  overlay.setMap(mapInstance.value)
  mapMarkers.value.push(overlay)
}

function drawRoute(points, stops = []) {
  if (!mapInstance.value || !window.kakao?.maps) return
  if (polyline.value) {
    try { polyline.value.setMap(null) } catch (_) {}
    polyline.value = null
  }
  clearMarkers()
  const pts = downsamplePath((points || []).filter((p) => isKoreaGps(p.lat, p.lng)))
  const stationStops = (stops || []).filter((s) => isKoreaGps(s.lat, s.lng))
  if (!pts.length && !stationStops.length) return
  lastDrawnRoute = { path: pts, stops: stationStops }
  const bounds = new window.kakao.maps.LatLngBounds()
  if (pts.length >= 2) {
    const path = pts.map((p) => new window.kakao.maps.LatLng(Number(p.lat), Number(p.lng)))
    polyline.value = new window.kakao.maps.Polyline({
      path, strokeWeight: 5, strokeColor: '#2f80ed', strokeOpacity: 0.9,
    })
    polyline.value.setMap(mapInstance.value)
    path.forEach((p) => bounds.extend(p))
  }
  const labelStops = stationStops.length
    ? stationStops
    : [pts[0], pts[pts.length - 1]].filter(Boolean)
  labelStops.forEach((s, i) => {
    addMarker(s.lat, s.lng, s.name || '')
    addStationLabel(s.lat, s.lng, `${i + 1}. ${s.name || s.code || ''}`)
    bounds.extend(new window.kakao.maps.LatLng(Number(s.lat), Number(s.lng)))
  })
  applyDriveBounds(bounds)
  placeSimOverlays()
}

function applyDriveBounds(bounds) {
  if (!mapInstance.value || !bounds) return
  try {
    mapInstance.value.setDraggable(true)
    mapInstance.value.setZoomable(true)
    mapInstance.value.setBounds(bounds)
  } catch (_) { /* ignore */ }
}

function redrawLastDriveRoute() {
  if (!lastDrawnRoute && pendingDriveRoute.value) {
    lastDrawnRoute = {
      path: pendingDriveRoute.value.path || [],
      stops: pendingDriveRoute.value.stops || [],
    }
  }
  if (lastDrawnRoute) drawRoute(lastDrawnRoute.path, lastDrawnRoute.stops)
}

function loadKakaoScript() {
  return new Promise((resolve, reject) => {
    const key = (import.meta.env.VITE_KAKAO_JS_KEY || '').trim()
    if (!key) return reject(new Error('NO_KEY'))
    if (window.kakao?.maps?.load) return resolve(key)
    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false&libraries=services`
    script.async = true
    script.onload = () => {
      let t = 0
      const w = () => {
        if (window.kakao?.maps?.load) resolve(key)
        else if (t++ < 40) setTimeout(w, 50)
        else reject(new Error('SDK_NOT_READY'))
      }
      w()
    }
    script.onerror = () => reject(new Error('SCRIPT_FAIL'))
    document.head.appendChild(script)
  })
}

let mapResizeObs = null
let mapResizeTimer = null
let mapDragging = false
let driveMapGen = 0
let lastDrawnRoute = null
let lastMapBox = { w: 0, h: 0 }

function goDrive() {
  tab.value = 'drive'
  nextTick(() => { mountDriveMap() })
}

function measureMapBox() {
  const el = mapEl.value
  const parent = el?.parentElement
  const w = Math.round(parent?.clientWidth || el?.clientWidth || 0)
  const h = Math.round(parent?.clientHeight || el?.clientHeight || 0)
  return { el, parent, w, h, ready: w >= 80 && h >= 80 }
}

function waitForMapBox(maxMs = 2500) {
  return new Promise((resolve) => {
    const t0 = Date.now()
    const tick = () => {
      const m = measureMapBox()
      if (m.ready) return resolve(true)
      if (Date.now() - t0 > maxMs) return resolve(false)
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
}

function ensureMapSize() {
  const m = measureMapBox()
  if (!m.el) return { w: 0, h: 0, changed: false, ready: false }
  if (!m.ready) return { w: m.w, h: m.h, changed: false, ready: false }
  const nextW = `${m.w}px`
  const nextH = `${m.h}px`
  const changed = m.el.style.width !== nextW || m.el.style.height !== nextH
  if (changed) {
    m.el.style.width = nextW
    m.el.style.height = nextH
  }
  return { w: m.w, h: m.h, changed, ready: true }
}

function fixMapRender({ keepCenter = true, force = false } = {}) {
  if (!mapInstance.value || !window.kakao?.maps) return
  if (mapDragging && !force) return
  try {
    const { changed, ready, w, h } = ensureMapSize()
    if (!ready) return
    const grewFromTiny = lastMapBox.h < 80 && h >= 80
    lastMapBox = { w, h }
    mapInstance.value.setDraggable(true)
    mapInstance.value.setZoomable(true)
    if (force || changed || grewFromTiny) {
      mapInstance.value.relayout()
    }
    if (grewFromTiny) {
      redrawLastDriveRoute()
      return
    }
    if (!keepCenter) {
      const o = stationByCode(me.value?.originCode)
        || (me.value?.currentLat != null
          ? { lat: me.value.currentLat, lng: me.value.currentLng }
          : stationByCode('200'))
      if (o?.lat != null) {
        mapInstance.value.setCenter(new window.kakao.maps.LatLng(o.lat, o.lng))
      }
    }
  } catch (_) { /* ignore */ }
}

function destroyDriveMap() {
  if (mapResizeObs) {
    try { mapResizeObs.disconnect() } catch (_) {}
    mapResizeObs = null
  }
  if (polyline.value) {
    try { polyline.value.setMap(null) } catch (_) {}
    polyline.value = null
  }
  clearMarkers()
  clearSimOverlays()
  mapInstance.value = null
  mapLoaded.value = false
  lastMapBox = { w: 0, h: 0 }
  if (mapEl.value) {
    mapEl.value.innerHTML = ''
    mapEl.value.removeAttribute('style')
  }
}

async function mountDriveMap({ remount = false } = {}) {
  const gen = ++driveMapGen
  if (tab.value !== 'drive') return
  if (remount || mapInstance.value) destroyDriveMap()
  await nextTick()
  if (gen !== driveMapGen || tab.value !== 'drive') return
  const sized = await waitForMapBox()
  if (gen !== driveMapGen || tab.value !== 'drive') return
  if (!sized) {
    const parent = mapEl.value?.parentElement
    if (parent) parent.style.minHeight = '360px'
    await waitForMapBox(800)
  }
  if (gen !== driveMapGen || tab.value !== 'drive') return
  await createDriveMap()
  if (gen !== driveMapGen) return
  const route = pendingDriveRoute.value
  if (route && (route.path?.length || route.stops?.length)) {
    requestAnimationFrame(() => {
      if (gen !== driveMapGen) return
      fixMapRender({ keepCenter: true, force: true })
      drawRoute(route.path || [], route.stops || [])
      bootstrapSimOffer()
      setTimeout(() => {
        if (gen !== driveMapGen || !mapInstance.value) return
        fixMapRender({ keepCenter: true, force: true })
        redrawLastDriveRoute()
      }, 160)
    })
  } else {
    fixMapRender({ keepCenter: false, force: true })
    bootstrapSimOffer()
  }
}

function bindMapDragGuards() {
  if (!mapInstance.value || !window.kakao?.maps?.event) return
  const maps = window.kakao.maps
  maps.event.addListener(mapInstance.value, 'dragstart', () => { mapDragging = true })
  maps.event.addListener(mapInstance.value, 'dragend', () => {
    mapDragging = false
    try {
      mapInstance.value.setDraggable(true)
      mapInstance.value.setZoomable(true)
    } catch (_) { /* ignore */ }
  })
  maps.event.addListener(mapInstance.value, 'idle', () => {
    mapDragging = false
  })
}

function bindMapResize() {
  if (mapResizeObs || !mapEl.value || typeof ResizeObserver === 'undefined') return
  mapResizeObs = new ResizeObserver(() => {
    if (tab.value !== 'drive' || mapDragging) return
    clearTimeout(mapResizeTimer)
    mapResizeTimer = setTimeout(() => {
      const before = lastMapBox.h
      fixMapRender({ keepCenter: true, force: true })
      if (before < 80 || Math.abs((lastMapBox.h || 0) - before) > 40) {
        redrawLastDriveRoute()
      }
    }, 120)
  })
  if (mapEl.value.parentElement) mapResizeObs.observe(mapEl.value.parentElement)
}

watch(gate, (g) => {
  if (g === 'route') loadTerminals({ force: !stations.value.length })
  if (g === 'app') startDemoPolling()
  else stopDemoPolling()
})

watch(tab, (t) => {
  if (t === 'drive') nextTick(() => { mountDriveMap({ remount: true }) })
  if (t === 'cargo') nextTick(() => initCargoMap())
})

watch(cartDockOpen, async () => {
  await nextTick()
  setTimeout(() => {
    relayoutCargoMap()
    if (cartPreview.value) drawCartRouteOnCargoMap(cartPreview.value)
  }, 100)
})

watch(activeTrip, () => { saveActiveTrip() }, { deep: true })
watch(spaceMeasured, () => { saveActiveTrip() })

watch(plannedOccupied, () => {
  const rem = simRemainingPercent()
  if (simOffer.value && !offerFitsRemaining(simOffer.value, rem)) {
    simOffer.value = null
    simNearby.value = (simNearby.value || []).filter((t) => offerFitsRemaining(t, rem))
    placeSimOverlays()
    saveActiveTrip()
  }
})

async function createDriveMap() {
  if (mapInstance.value) {
    fixMapRender({ keepCenter: true, force: true })
    return
  }
  if (tab.value !== 'drive' || !mapEl.value) return
  mapMessage.value = '지도 로딩...'
  try {
    await loadKakaoScript()
    await new Promise((resolve) => window.kakao.maps.load(() => resolve()))
    await nextTick()
    if (!mapEl.value || tab.value !== 'drive') return
    const sized = ensureMapSize()
    if (!sized.ready) return
    const o = stationByCode(me.value?.originCode) || stationByCode('200') || { lat: 35.1151, lng: 129.0413, name: '부산' }
    const center = new window.kakao.maps.LatLng(o.lat, o.lng)
    mapInstance.value = new window.kakao.maps.Map(mapEl.value, {
      center,
      level: 7,
      draggable: true,
      scrollwheel: true,
      disableDoubleClickZoom: false,
    })
    try {
      mapInstance.value.setDraggable(true)
      mapInstance.value.setZoomable(true)
      const mapTypeControl = new window.kakao.maps.MapTypeControl()
      mapInstance.value.addControl(mapTypeControl, window.kakao.maps.ControlPosition.TOPRIGHT)
      const zoomControl = new window.kakao.maps.ZoomControl()
      mapInstance.value.addControl(zoomControl, window.kakao.maps.ControlPosition.RIGHT)
    } catch (_) { /* ignore */ }
    bindMapDragGuards()
    bindMapResize()
    mapLoaded.value = true
    mapMessage.value = '지도 로드 완료'
    lastMapBox = { w: sized.w, h: sized.h }
    mapInstance.value.relayout()
    mapInstance.value.setCenter(center)
  } catch (err) {
    mapMessage.value = '지도 표시 실패'
    mapHint.value = String(err.message || err)
  }
}

onMounted(async () => {
  window.addEventListener('storage', onDemoResetStorage)
  startClockTick()
  await loadTerminals()
  const ok = await restoreSession()
  if (!ok) gate.value = 'login'
})

onUnmounted(() => {
  window.removeEventListener('storage', onDemoResetStorage)
  stopClockTick()
  stopFeedPolling()
  stopDemoPolling()
  stopBusyAnim()
  if (mapResizeObs) {
    try { mapResizeObs.disconnect() } catch (_) {}
    mapResizeObs = null
  }
})
</script>

<style>
:root {
  --kakao-yellow: #ffcd00;
  --kakao-black: #3c3c3c;
  --kakao-bg: #f2f2f2;
  --kakao-blue: #2f80ed;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: "Pretendard", "Apple SD Gothic Neo", sans-serif; }
.kakao-app {
  max-width: 480px; margin: 0 auto; min-height: 100vh;
  background: var(--kakao-bg); color: var(--kakao-black); position: relative;
}
.kakao-app.drive-lock {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  max-height: 100dvh;
  overflow: hidden;
  overscroll-behavior: none;
}
.k-main { padding-bottom: 72px; }
.kakao-app.drive-lock .k-header {
  flex-shrink: 0;
}
.kakao-app.drive-lock .k-main {
  flex: 1;
  min-height: 0;
  padding-bottom: 58px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.kakao-app.drive-lock .tab-drive {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
}
.kakao-app.drive-lock .drive-stage {
  flex: 0 0 100%;
  height: 100%;
  max-height: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.kakao-app.drive-lock .map-container {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
  max-height: none;
  touch-action: pan-x pan-y pinch-zoom;
  overscroll-behavior: contain;
}
.kakao-app.drive-lock .drive-dock {
  flex: 0 0 auto;
  height: auto;
  min-height: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
}
.kakao-app.drive-lock .drive-more {
  flex: 0 0 auto;
}
.kakao-app.drive-lock .k-bottom-nav {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 0;
  width: min(480px, 100%);
  z-index: 40;
}
.gate { padding-top: 48px; }
.gate-brand { font-size: 32px; font-weight: 900; margin: 0 0 8px; }
.gate h2 { margin: 0 0 8px; }
.gate-desc { color: #777; font-size: 13px; margin-bottom: 20px; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 12px; margin-bottom: 12px; }
.field input, .field select {
  padding: 12px; border: 1px solid #ddd; border-radius: 10px; font-size: 15px;
}
.k-header { background: #fff; padding: 10px 12px 6px; position: sticky; top: 0; z-index: 20; }
.top-nav { display: flex; align-items: center; gap: 8px; }
.brand { font-weight: 900; font-size: 18px; }
.me-chip { flex: 1; min-width: 0; font-size: 12px; font-weight: 700; }
.me-chip .sub { display: block; color: #888; font-weight: 500; font-size: 11px; }
.demo-trigger {
  background: var(--kakao-yellow); border: none; border-radius: 8px;
  padding: 6px 10px; font-weight: 700; font-size: 12px; cursor: pointer;
}
.link-btn { border: none; background: none; color: #888; font-size: 11px; cursor: pointer; }
.route-bar {
  margin: 8px 0 0; font-size: 12px; font-weight: 700; color: #444;
  background: #f7f7f7; padding: 8px 10px; border-radius: 8px; cursor: pointer;
}
.route-bar .edit { float: right; color: var(--kakao-blue); font-weight: 600; }
.p-12 { padding: 12px; } .p-16 { padding: 16px; }
.list-head { display: flex; justify-content: space-between; align-items: center; }
.list-head h3 { margin: 0; font-size: 16px; }
.kakao-app.cargo-lock {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  max-height: 100dvh;
  overflow: hidden;
  overscroll-behavior: none;
}
.kakao-app.cargo-lock .k-header { flex-shrink: 0; }
.kakao-app.cargo-lock .k-main {
  flex: 1;
  min-height: 0;
  padding-bottom: 58px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.kakao-app.cargo-lock .tab-cargo {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding-bottom: 0;
}
.kakao-app.cargo-lock .k-bottom-nav {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 0;
  width: min(480px, 100%);
  z-index: 40;
}
.cart-route-overlay {
  position: absolute; left: 10px; right: 10px; top: 10px; z-index: 4;
  background: rgba(60,60,60,.88); color: #fff; border-radius: 10px; padding: 8px 10px;
  pointer-events: none;
}
.cart-route-overlay .direction { font-size: 14px; font-weight: 800; display: flex; gap: 10px; }
.cart-route-overlay .next-step,
.cart-route-overlay .route-line { margin: 3px 0 0; font-size: 11px; line-height: 1.35; }
.cart-row {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 8px; padding: 8px 0; border-bottom: 1px solid #f0f0f0;
}
.tab-cargo {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.cargo-top {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 4px;
}
.cargo-top h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 800;
  white-space: nowrap;
}
.mode-inline {
  display: flex;
  gap: 4px;
  flex: 1;
  min-width: 0;
}
.mode-chip {
  border: 1.5px solid #ddd;
  background: #fff;
  border-radius: 8px;
  padding: 6px 8px;
  font-weight: 700;
  font-size: 12px;
  cursor: pointer;
  color: #555;
}
.mode-chip.sm {
  flex: 0 0 auto;
  padding: 5px 9px;
  font-size: 11px;
}
.mode-chip.on { border-color: #2f80ed; background: #eaf2ff; color: #1a5bb8; }
.cart-badge {
  flex-shrink: 0;
  border: none;
  font-size: 11px;
  font-weight: 800;
  color: #1a5bb8;
  background: #eaf2ff;
  padding: 5px 8px;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.cart-badge.empty { color: #888; background: #f0f0f0; }
.cart-badge.open { background: #2f80ed; color: #fff; }
.cart-badge .caret { font-size: 9px; opacity: 0.85; }
.px-12 { padding-left: 12px; padding-right: 12px; }
.pt-8 { padding-top: 8px; }
.pb-0 { padding-bottom: 0; }
.mb-8 { margin-bottom: 8px; }
.cargo-map-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  margin: 0 8px;
  display: flex;
  flex-direction: column;
}
.cargo-map-wrap {
  position: relative;
  flex: 1;
  min-height: 200px;
  border-radius: 12px;
  overflow: hidden;
  background: #dfe6ee;
}
.cargo-map-canvas { position: absolute; inset: 0; min-height: 200px; }
.cargo-map-ph { position: absolute; inset: 0; z-index: 1; }
.cargo-opt-btn {
  position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 5;
  box-shadow: 0 4px 16px rgba(0,0,0,.15);
}
.cargo-map-sheet {
  position: absolute;
  left: 8px; right: 8px; top: 8px;
  z-index: 7;
  max-height: min(58%, 420px);
  display: flex;
  flex-direction: column;
  background: rgba(255,255,255,.97);
  border-radius: 14px;
  padding: 10px 12px;
  box-shadow: 0 6px 24px rgba(0,0,0,.14);
}
.cargo-map-sheet-body {
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  min-height: 0;
  flex: 1;
}
.empty-box.compact { padding: 16px; font-size: 13px; }
.cargo-dock {
  flex-shrink: 0;
  margin: 6px 8px 8px;
  padding: 8px 10px;
  background: #fff;
  border-radius: 12px;
  border: 2px solid #2f80ed;
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: 30vh;
}
.cargo-dock.collapsed {
  max-height: none;
}
.cargo-dock-toggle {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  border: none;
  background: transparent;
  padding: 0 0 6px;
  text-align: left;
  cursor: pointer;
}
.cargo-dock-toggle strong { font-size: 13px; }
.cargo-dock-toggle .sub {
  display: block;
  font-size: 11px;
  color: #888;
  font-weight: 500;
  margin-top: 2px;
}
.cargo-dock-toggle .caret {
  flex-shrink: 0;
  font-size: 11px;
  color: #2f80ed;
  font-weight: 700;
  padding-top: 2px;
}
.cargo-dock-body {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-bottom: 6px;
}
.cargo-dock-list {
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  min-height: 0;
  flex: 1;
  max-height: 22vh;
}
.cargo-dock-empty {
  margin: 0 0 4px;
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}
.cargo-confirm-btn {
  flex-shrink: 0;
  padding: 10px !important;
  font-size: 13px !important;
}
.cluster-pick {
  position: absolute; left: 10px; right: 10px; top: 10px; z-index: 6;
  max-height: 40%; overflow-y: auto; background: #fff; border-radius: 12px; padding: 10px;
}
.cluster-pick-item {
  display: block; width: 100%; text-align: left; border: none; background: #f7f7f7;
  margin-top: 6px; padding: 8px 10px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.cluster-pick-item:active { background: #eaf2ff; }
.cargo-sheet {
  margin: 12px; padding: 12px; background: #fff; border-radius: 14px;
  max-height: 42vh; overflow-y: auto;
}
.sheet-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 10px;
}
.sheet-head .sub { display: block; font-size: 11px; color: #888; font-weight: 500; margin-top: 2px; }
.k-btn {
  border: none; border-radius: 10px; padding: 12px; font-weight: 700; cursor: pointer; font-size: 14px;
}
.k-btn.primary { background: var(--kakao-yellow); color: var(--kakao-black); }
.k-btn.outline { background: #fff; border: 1.5px solid #eee; }
.k-btn.gray { background: #eee; color: #666; }
.k-btn.sm { padding: 6px 10px; font-size: 12px; }
.k-btn.w-full, .w-full { width: 100%; }
.flex-1 { flex: 1; } .flex-2 { flex: 2; }
.row { display: flex; } .gap-8 { gap: 8px; } .mt-8 { margin-top: 8px; } .mt-16 { margin-top: 16px; } .mb-16 { margin-bottom: 16px; }
.desc.subtle { font-size: 12px; color: #888; margin: 6px 0 12px; }
.empty-box { padding: 24px; text-align: center; color: #888; background: #fff; border-radius: 12px; }
.cargo-card {
  background: #fff; border-radius: 14px; padding: 12px; margin-bottom: 10px; cursor: pointer;
}
.cc-route { font-weight: 800; font-size: 14px; margin-bottom: 6px; }
.cc-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #555; margin-top: 4px; }
.cc-meta .plus { color: var(--kakao-blue); font-weight: 800; }
.cc-meta .esg { color: #0b6e4f; font-weight: 700; }
.od-item-list { max-height: 50vh; overflow-y: auto; }
.od-item-row {
  padding: 10px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px;
}
.od-item-row .oid { font-weight: 800; }
.od-item-row .ometa { color: #555; margin-top: 2px; }
.od-item-row .ostatus { color: #888; font-size: 12px; margin-top: 2px; }
.cargo-photo-modal { max-width: 92vw; }
.cargo-photo-img {
  display: block;
  width: 100%;
  max-height: 55vh;
  object-fit: contain;
  border-radius: 10px;
  background: #111;
  margin-top: 8px;
}
.tab-drive {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--kakao-bg);
}
.drive-stage {
  display: flex;
  flex-direction: column;
  width: 100%;
  background: var(--kakao-bg);
}
.map-container {
  width: 100%;
  position: relative;
  background: #dfe6ee;
  overflow: hidden;
  flex: 4 1 0;
  min-height: 240px;
  z-index: 2;
  touch-action: pan-x pan-y pinch-zoom;
  overscroll-behavior: contain;
}
.map-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: auto;
  touch-action: pan-x pan-y pinch-zoom;
  cursor: grab;
}
.map-canvas,
.map-canvas div,
.map-canvas img {
  box-sizing: content-box;
  max-width: none;
}
.map-canvas:active {
  cursor: grabbing;
}
.map-placeholder {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; z-index: 1; background: rgba(223,230,238,.9);
  pointer-events: none;
}
.map-placeholder .hint { font-size: 11px; color: #666; }
.navi-overlay {
  position: absolute; left: 10px; right: 10px; top: 10px; z-index: 2;
  background: rgba(60,60,60,.88); color: #fff; border-radius: 12px; padding: 10px 12px;
  pointer-events: none;
}
.sim-step-btn {
  position: absolute;
  right: 10px;
  bottom: 12px;
  z-index: 3;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 22px;
  background: #2f80ed;
  color: #fff;
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, .28);
  cursor: pointer;
}
.sim-step-btn:disabled {
  background: #9aa8b8;
  cursor: default;
}
.sim-truck-pin {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #1a73e8;
  border: 3px solid #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, .35);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  line-height: 1;
}
.sim-opp-pin {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 4px 8px;
  background: #fff7e6;
  border: 2px solid #f2994a;
  border-radius: 8px;
  color: #8a4b00;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
  box-shadow: 0 2px 6px rgba(0, 0, 0, .2);
}
.sim-opp-pin span { color: #d35400; }
.direction { font-size: 16px; font-weight: 800; display: flex; flex-wrap: wrap; gap: 8px 10px; }
.direction .time { font-size: 14px; font-weight: 700; }
.next-step, .route-line { margin: 4px 0 0; font-size: 12px; }
.drive-dock {
  flex: 0 0 auto;
  padding: 8px 10px 10px;
  background: var(--kakao-bg);
  display: flex;
  flex-direction: column;
}
.drive-dock .stop-panel {
  margin: 0;
  padding: 10px 12px;
  gap: 6px;
}
.drive-more {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 12px 20px;
  background: var(--kakao-bg);
}
.drive-actions { padding: 0 2px; }
.stop-panel {
  background: #fff;
  border-radius: 14px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.stop-panel.muted {
  background: #f7f7f7;
}
.stop-now {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}
.stop-phase {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef5ff;
  color: #2f80ed;
}
.stop-idx {
  font-size: 11px;
  color: #999;
  font-variant-numeric: tabular-nums;
}
.stop-od {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0;
}
.stop-od-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.stop-od-row strong {
  flex: 1;
  font-size: 13px;
  line-height: 1.25;
  word-break: keep-all;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stop-od-arrow {
  color: #bbb;
  font-size: 11px;
  padding-left: 28px;
  line-height: 1;
}
.od-tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  min-width: 36px;
  text-align: center;
}
.od-tag.from {
  background: #eef5ff;
  color: #2f80ed;
}
.od-tag.to {
  background: #fff4e5;
  color: #c47820;
}
.stop-hint {
  margin: 0;
  font-size: 11px;
  color: #c47820;
}
.stop-hint.muted {
  color: #888;
}
.stop-step-hint {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: #3c3c3c;
  line-height: 1.35;
}
.stop-actions {
  display: flex;
  gap: 6px;
  justify-content: stretch;
  flex-wrap: nowrap;
  margin-top: 2px;
}
.stop-actions .k-btn {
  min-width: 0;
  flex: 1 1 0;
  padding: 8px 6px;
  font-size: 12px;
  white-space: nowrap;
}
.stop-actions .k-btn:disabled,
.stop-actions .photo-btn.is-disabled {
  opacity: 0.38;
  cursor: not-allowed;
  pointer-events: none;
  filter: grayscale(0.35);
  background: #f3f3f3 !important;
  color: #999 !important;
  border-color: #e5e5e5 !important;
}
.stop-actions .k-btn.primary:not(:disabled) {
  box-shadow: 0 2px 0 rgba(0, 0, 0, 0.08);
}
.stop-actions .photo-btn.need {
  border-color: #f5c400;
  font-weight: 800;
}
.stop-actions .photo-btn.done {
  border-color: #27ae60;
  color: #1e8449;
  font-weight: 700;
}
.status-card {
  margin: 0;
  background: #fff;
  border-radius: 16px;
  padding: 14px;
  position: relative;
  z-index: 1;
}
.truck-info { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.tag { background: #eee; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700; }
.number { font-weight: 800; }
.status-badge { margin-left: auto; font-size: 12px; padding: 4px 8px; border-radius: 12px; background: #f2f2f2; }
.status-badge.MOVING { background: #e3f2fd; color: #1976d2; }
.label-row { display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; }
.label-row.sub { margin-top: 6px; color: #888; font-weight: 500; }
.progress-bar { height: 8px; background: #eee; border-radius: 4px; margin: 8px 0; overflow: hidden; }
.progress-bar .fill { height: 100%; background: var(--kakao-yellow); transition: width .3s; }
.guide { margin-top: 10px; padding: 10px; background: #fff9e0; border-radius: 8px; font-size: 13px; }
.shadow { box-shadow: 0 4px 16px rgba(0,0,0,.06); }
.k-modal-bottom {
  position: fixed; left: 50%; transform: translateX(-50%); bottom: 64px;
  width: min(480px, 100%); background: #fff; border-radius: 20px 20px 0 0; padding: 12px 16px 20px; z-index: 30;
}
.handle { width: 40px; height: 4px; background: #eee; margin: 0 auto 12px; border-radius: 2px; }
.proposal-header { display: flex; align-items: center; gap: 8px; }
.proposal-header h3 { margin: 0; font-size: 16px; }
.badge-new { background: #ff4b4b; color: #fff; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 800; }
.badge-race { margin-left: auto; background: #fff3cd; color: #856404; font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
.briefing-box { background: #f9f9f9; padding: 12px; border-radius: 12px; margin: 12px 0; font-size: 14px; }
.mini-stats { padding-left: 18px; font-size: 13px; color: #555; line-height: 1.6; }
.price-row { display: flex; justify-content: space-between; margin: 12px 0 16px; font-weight: 700; }
.price { font-size: 20px; font-weight: 900; color: var(--kakao-blue); }
.slide-up-enter-active, .slide-up-leave-active { transition: transform .25s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translate(-50%, 100%); }
.k-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 40;
  display: flex; align-items: center; justify-content: center;
}
.k-modal-center {
  width: 92%; max-width: 420px; max-height: 90vh; overflow-y: auto;
  background: #fff; border-radius: 20px; padding: 18px;
}
.form-row label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; margin-bottom: 8px; }
.form-row select, .form-row input { padding: 10px; border: 1px solid #ddd; border-radius: 8px; }
.via-box { margin: 8px 0; }
.via-label { font-size: 12px; color: #555; }
.via-list { display: flex; flex-wrap: wrap; gap: 6px; max-height: 100px; overflow-y: auto; }
.via-chip {
  display: inline-flex; align-items: center; gap: 4px; font-size: 11px;
  padding: 6px 8px; border: 1px solid #ddd; border-radius: 8px; background: #fafafa;
}
.via-chip.on { border-color: #2f80ed; background: #eaf2ff; font-weight: 700; }
.via-chip.disabled { opacity: .45; }
.cargo-selector { max-height: 160px; overflow-y: auto; border: 1px solid #eee; border-radius: 12px; margin: 8px 0; }
.cargo-item { padding: 10px; border-bottom: 1px solid #f5f5f5; display: flex; gap: 8px; font-size: 12px; cursor: pointer; }
.cargo-item.selected { background: #fff9e0; border-left: 4px solid var(--kakao-yellow); }
.cargo-item .id { font-weight: 700; flex: 1; }
.cargo-item .vol { color: var(--kakao-blue); font-weight: 700; }
.k-bottom-nav {
  position: fixed; left: 50%; transform: translateX(-50%); bottom: 0;
  width: min(480px, 100%); height: 58px; background: #fff;
  display: flex; border-top: 1px solid #eee; z-index: 25;
}
.nav-item { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; cursor: pointer; }
.nav-item.active { color: var(--kakao-black); font-weight: 800; }
.nav-item .label { font-size: 12px; }
.log-container { margin: 8px 14px 16px; border-radius: 12px; background: #f9f9f9; }
.log-header {
  padding: 10px 14px; font-size: 12px; font-weight: 700;
  display: flex; justify-content: space-between; cursor: pointer;
}
.log-toggle { color: #888; font-size: 11px; }
.log-content {
  height: 100px; padding: 0 14px 10px; font-family: ui-monospace, Consolas, monospace;
  font-size: 10px; overflow-y: auto; color: #555;
}
.k-card { background: #fff; border-radius: 16px; padding: 16px; }
.ledger-list { margin: 12px 0; display: flex; flex-direction: column; gap: 10px; }
.ledger-sub {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 800;
  color: #3c3c3c;
}
.ledger-row { background: #f7f7f7; border-radius: 12px; padding: 12px; }
.ledger-row-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.ledger-no {
  font-size: 11px;
  font-weight: 800;
  color: #2f80ed;
}
.ledger-time {
  font-size: 11px;
  color: #999;
}
.ledger-row .route { font-weight: 700; font-size: 13px; margin-bottom: 6px; line-height: 1.35; }
.ledger-od {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #555;
  margin-bottom: 6px;
}
.ledger-od .arrow { color: #bbb; }
.ledger-od .od-tag {
  display: inline-block;
  margin-right: 4px;
  font-style: normal;
}
.ledger-meta {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  font-size: 11px;
  color: #888;
}
.ledger-row .amt { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; }
.ledger-row .plus { color: var(--kakao-blue); font-weight: 700; }
.ledger-row .net { font-weight: 800; color: #3c3c3c; }
.ledger-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px; }
.ledger-grid .item label { font-size: 12px; color: #888; }
.ledger-grid .val { margin: 4px 0 0; font-size: 18px; font-weight: 800; }
.ledger-grid .plus { color: var(--kakao-blue); }
.ledger-grid .esg { color: #0b6e4f; }
.busy-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.busy-card { background: #fff; border-radius: 16px; padding: 20px; width: 80%; max-width: 300px; }
.busy-title { margin: 0 0 12px; font-weight: 800; font-size: 15px; }
.progress-track { height: 10px; background: #eee; border-radius: 6px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #ffcd00, #2f80ed); transition: width .25s; }
.busy-sub { margin: 10px 0 0; font-size: 12px; color: #777; }
.toast {
  position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
  width: min(420px, 92%); background: #1a1a1a; color: #fff;
  border-radius: 12px; padding: 12px 14px; z-index: 90; cursor: pointer;
}
.toast strong { color: var(--kakao-yellow); font-size: 12px; }
.toast p { margin: 4px 0 0; font-size: 13px; }
.toast-offer { cursor: default; }
.toast-rem { margin: 6px 0 0; font-size: 12px; color: #666; }
.toast-actions { margin-top: 10px; display: flex; justify-content: flex-end; gap: 8px; }
.toast-actions .k-btn { min-width: 72px; }
</style>
