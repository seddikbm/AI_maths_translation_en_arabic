import { LoaderCircle } from "lucide-react";

interface ProgressOverlayProps {
  progress: number;
  label: string;
}

export function ProgressOverlay({ progress, label }: ProgressOverlayProps) {
  return (
    <div className="progress-shell" aria-live="polite">
      <div className="progress-copy">
        <LoaderCircle className="spin" size={16} />
        <span>{label}</span>
      </div>
      <div className="progress-bar" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
