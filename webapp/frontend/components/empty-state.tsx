export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="empty-state">
      <h3 className="empty-title">{title}</h3>
      <p className="empty-message">{message}</p>
    </div>
  );
}
