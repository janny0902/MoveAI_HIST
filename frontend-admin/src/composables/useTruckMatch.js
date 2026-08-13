import { ref } from 'vue'
import { matchByTruck } from '../lib/api'
import { pushTruckLocation } from '../lib/rematch'

export function useTruckMatch() {
  const matching = ref(null)
  const busy = ref(false)
  const error = ref(null)
  const ranAt = ref(null)
  let seq = 0

  async function run(truckId, position, candidateLimit, palletized) {
    const my = ++seq
    busy.value = true
    error.value = null
    try {
      if (position) await pushTruckLocation(truckId, position)
      const result = await matchByTruck(truckId, candidateLimit, palletized)
      if (my !== seq) return null
      matching.value = result
      ranAt.value = new Date()
      return result
    } catch (e) {
      if (my === seq) error.value = e.message || '매칭에 실패했습니다.'
      return null
    } finally {
      if (my === seq) busy.value = false
    }
  }

  function reset() {
    seq += 1
    matching.value = null
    error.value = null
    ranAt.value = null
    busy.value = false
  }

  return { matching, busy, error, ranAt, run, reset }
}
