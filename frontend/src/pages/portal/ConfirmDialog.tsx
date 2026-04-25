type ConfirmDialogProps = {
  body: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
  open: boolean;
  title: string;
};

export function ConfirmDialog({
  body,
  confirmLabel,
  onCancel,
  onConfirm,
  open,
  title,
}: ConfirmDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="confirm-dialog-backdrop" role="presentation">
      <div aria-modal="true" className="confirm-dialog" role="dialog" aria-label={title}>
        <strong>{title}</strong>
        <p>{body}</p>
        <div className="confirm-dialog__actions">
          <button className="ghost-action ghost-action--bright" onClick={onCancel}>
            取消
          </button>
          <button className="ghost-action ghost-action--danger" onClick={() => void onConfirm()}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
