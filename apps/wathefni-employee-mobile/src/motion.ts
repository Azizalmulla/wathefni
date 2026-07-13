import { useEffect, useState } from 'react'
import { AccessibilityInfo, Easing } from 'react-native'

export const motion = {
  duration: {
    instant: 120,
    quick: 180,
    enter: 280,
    progress: 420,
  },
  easing: {
    standard: Easing.bezier(0.2, 0.8, 0.2, 1),
    exit: Easing.bezier(0.4, 0, 1, 1),
  },
  spring: {
    speed: 28,
    bounciness: 3,
  },
} as const

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    let mounted = true
    void AccessibilityInfo.isReduceMotionEnabled().then((value) => {
      if (mounted) setReduced(value)
    })
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced)
    return () => {
      mounted = false
      subscription.remove()
    }
  }, [])

  return reduced
}
