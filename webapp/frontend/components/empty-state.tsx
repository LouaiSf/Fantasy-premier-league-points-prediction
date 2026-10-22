import Link from "next/link";
import type { ReactNode } from "react";

/** Every empty or failed state says why, and offers the way out. */
export function EmptyState({
  title,
  message,
  icon,
  action,
}: {
  title: string;
  message: string;
  icon?: ReactNode;
  action?: { label: string; href?: string; onClick?: () => void };
}) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-icon" aria-hidden="true">{icon}</div>}
      <h3 className="empty-title">{title}</h3>
      <p className="empty-message">{message}</p>
      {action && (action.href ? (
        <Link className="btn sm" href={action.href}>{action.label}</Link>
      ) : (
        <button type="button" className="btn sm" onClick={action.onClick}>{action.label}</button>
      ))}
    </div>
  );
}
