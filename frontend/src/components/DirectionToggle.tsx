import { ArrowLeftRight } from "lucide-react";
import type { Direction } from "../services/api";

interface DirectionToggleProps {
  direction: Direction;
  onChange: (direction: Direction) => void;
}

export function DirectionToggle({ direction, onChange }: DirectionToggleProps) {
  return (
    <div className="segmented-control" role="tablist" aria-label="Translation direction">
      <button
        type="button"
        className={direction === "en2ar" ? "active" : ""}
        onClick={() => onChange("en2ar")}
      >
        <ArrowLeftRight size={16} />
        <span>EN to AR</span>
      </button>
      <button
        type="button"
        className={direction === "ar2en" ? "active" : ""}
        onClick={() => onChange("ar2en")}
      >
        <ArrowLeftRight size={16} />
        <span>AR to EN</span>
      </button>
    </div>
  );
}
