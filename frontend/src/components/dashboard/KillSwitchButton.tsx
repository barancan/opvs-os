import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { activateKillSwitch } from '@/api/killswitch'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/stores/useAppStore'

const idleStyle: React.CSSProperties = {
  boxShadow:
    '0 0 24px 6px rgba(220, 38, 38, 0.55), 0 0 8px 2px rgba(220, 38, 38, 0.4)',
}

const armedStyle: React.CSSProperties = {
  boxShadow:
    '0 0 32px 10px rgba(220, 38, 38, 0.8), 0 0 0 3px rgba(255,255,255,0.6), 0 0 12px 4px rgba(220, 38, 38, 0.9)',
}

const activeStyle: React.CSSProperties = {
  boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.8)',
}

export function KillSwitchButton() {
  const killSwitchActive = useAppStore((s) => s.killSwitchActive)
  const killSwitchArmed = useAppStore((s) => s.killSwitchArmed)
  const setKillSwitchActive = useAppStore((s) => s.setKillSwitchActive)
  const setKillSwitchArmed = useAppStore((s) => s.setKillSwitchArmed)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { mutate: activate, isPending: isActivating } = useMutation({
    mutationFn: activateKillSwitch,
    onSuccess: () => {
      setKillSwitchActive(true)
      setKillSwitchArmed(false)
    },
  })

  // Cancel auto-reset timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [])

  function handleClick() {
    if (killSwitchActive) return

    if (!killSwitchArmed) {
      setKillSwitchArmed(true)
      timerRef.current = setTimeout(() => {
        setKillSwitchArmed(false)
        timerRef.current = null
      }, 5000)
    } else {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      setKillSwitchArmed(false)
      activate()
    }
  }

  const buttonStyle = killSwitchActive
    ? activeStyle
    : killSwitchArmed
      ? armedStyle
      : idleStyle

  const animationName = killSwitchActive
    ? 'none'
    : killSwitchArmed
      ? 'breathe-fast'
      : 'breathe-slow'

  const animationDuration = killSwitchArmed ? '1s' : '4s'

  return (
    <>
      <style>{`
        @keyframes breathe-slow {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }
        @keyframes breathe-fast {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
      <div className="flex flex-col items-center gap-2">
        <button
          onClick={handleClick}
          disabled={isActivating}
          style={{
            ...buttonStyle,
            animationName,
            animationDuration,
            animationTimingFunction: 'ease-in-out',
            animationIterationCount: 'infinite',
            width: 36,
            height: 36,
          }}
          className={cn(
            'rounded-[18px] border-0 cursor-pointer transition-all duration-300 disabled:cursor-not-allowed',
            killSwitchActive ? 'bg-zinc-800' : 'bg-red-700',
          )}
          aria-label={
            killSwitchActive
              ? 'Kill switch is active'
              : killSwitchArmed
                ? 'Click to confirm kill switch'
                : 'Activate kill switch'
          }
        />
        {killSwitchArmed && !killSwitchActive && (
          <span className="text-xs text-amber-400 animate-pulse">
            Click again to confirm
          </span>
        )}
        {killSwitchActive && (
          <span className="text-xs text-red-800">Kill switch active</span>
        )}
      </div>
    </>
  )
}
