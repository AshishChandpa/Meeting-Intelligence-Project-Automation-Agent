import { HTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'

export interface BadgeProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'high' | 'medium' | 'low' | 'outline'
}

export const Badge = forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = 'default', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors',
          {
            'bg-primary text-primary-foreground hover:bg-primary/80': variant === 'default',
            'bg-green-500 text-white hover:bg-green-600': variant === 'high',
            'bg-yellow-500 text-white hover:bg-yellow-600': variant === 'medium',
            'bg-red-500 text-white hover:bg-red-600': variant === 'low',
            'border border-foreground text-foreground': variant === 'outline',
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