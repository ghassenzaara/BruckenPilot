import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function Widget({
  title,
  icon,
  action,
  children,
  className,
}: {
  title?: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('animate-in-up rounded-2xl border bg-card/60 p-4', className)}>
      {title && (
        <div className="mb-3 flex items-center gap-2">
          {icon && <span className="text-primary">{icon}</span>}
          <h3 className="text-base font-bold tracking-tight">{title}</h3>
          {action && <div className="ml-auto">{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

/** label / value pair used in the Stammdaten list */
export function Stat({ label, value }: { label: string; value?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/50 pb-3 last:border-0 last:pb-0">
      <p className="shrink-0 text-sm font-medium text-muted-foreground">{label}</p>
      <p className="truncate text-base font-bold text-right">{value ?? '—'}</p>
    </div>
  );
}
