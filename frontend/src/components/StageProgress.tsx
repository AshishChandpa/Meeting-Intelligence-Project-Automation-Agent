import { Check, Circle, Lock } from 'lucide-react'
import type { Stage } from '@/types'
import { cn } from '@/lib/utils'

interface StageProgressProps {
  currentStage: Stage
}

const STAGES: { key: Stage; label: string; description: string }[] = [
  { key: 'parse', label: '1. Parse', description: 'Extract requirements' },
  { key: 'clarify', label: '2. Clarify', description: 'Answer questions' },
  { key: 'sow', label: '3. SoW', description: 'Scope of Work' },
  { key: 'sprint', label: '4. Sprint', description: 'Task breakdown' },
  { key: 'jira', label: '5. Jira', description: 'Sync to Jira' },
  { key: 'done', label: '6. Done', description: 'Pipeline complete' },
]

export function StageProgress({ currentStage }: StageProgressProps) {
  const currentIndex = STAGES.findIndex((s) => s.key === currentStage)

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-4">
      {STAGES.map((stage, index) => {
        const isComplete = index < currentIndex
        const isCurrent = index === currentIndex
        const isLocked = index > currentIndex

        return (
          <div key={stage.key} className="flex items-center">
            <div
              className={cn(
                'flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                {
                  'bg-primary text-primary-foreground': isCurrent,
                  'bg-muted text-muted-foreground': isComplete,
                  'border-dashed opacity-50': isLocked,
                },
              )}
            >
              {isComplete ? (
                <Check className="h-4 w-4" />
              ) : isLocked ? (
                <Lock className="h-4 w-4" />
              ) : (
                <Circle className="h-4 w-4" />
              )}
              <div className="flex flex-col">
                <span className="font-medium">{stage.label}</span>
                <span className="text-xs opacity-80">{stage.description}</span>
              </div>
            </div>
            {index < STAGES.length - 1 && (
              <div className="mx-1 h-px w-8 bg-border" />
            )}
          </div>
        )
      })}
    </div>
  )
}