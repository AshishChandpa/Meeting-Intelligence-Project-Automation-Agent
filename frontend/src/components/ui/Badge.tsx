import { HTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'

export interface BadgeProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'high' | 'medium' | 'low' | 'outline' | 'secondary' | 'primary' | 'destructive' | 'info' | 'success' | 'warning'
}

export const Badge = forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = 'default', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
          {
            'border-primary/20 bg-primary/10 text-primary': variant === 'default' || variant === 'primary',
            'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/80 dark:bg-emerald-950/40 dark:text-emerald-300': variant === 'high' || variant === 'success',
            'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/80 dark:bg-amber-950/40 dark:text-amber-300': variant === 'medium' || variant === 'warning',
            'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/80 dark:bg-rose-950/40 dark:text-rose-300': variant === 'low' || variant === 'destructive',
            'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/80 dark:bg-sky-950/40 dark:text-sky-300': variant === 'info',
            'border-border bg-background text-foreground': variant === 'outline',
            'border-border bg-secondary text-secondary-foreground': variant === 'secondary',
          },
          className,
        )}
        {...props}
      >
        {children}
      </div>
    )
  },
)

Badge.displayName = 'Badge'