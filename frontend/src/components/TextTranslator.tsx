import { SendHorizontal } from "lucide-react";
import { DirectionToggle } from "./DirectionToggle";

interface TextTranslatorProps {
  direction: "en2ar" | "ar2en";
  sourceText: string;
  previewDirection: string;
  onDirectionChange: (direction: "en2ar" | "ar2en") => void;
  onSourceTextChange: (value: string) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export function TextTranslator({
  direction,
  sourceText,
  previewDirection,
  onDirectionChange,
  onSourceTextChange,
  onSubmit,
  isSubmitting
}: TextTranslatorProps) {
  return (
    <section className="panel composer-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Text</p>
          <h2>{previewDirection}</h2>
        </div>
        <DirectionToggle direction={direction} onChange={onDirectionChange} />
      </div>
      <label className="field-label" htmlFor="text-source">
        Source
      </label>
      <textarea
        id="text-source"
        className="editor"
        dir={direction === "ar2en" ? "rtl" : "ltr"}
        placeholder={direction === "en2ar" ? "Paste English math text." : "الصق نصا رياضيا بالعربية."}
        value={sourceText}
        onChange={(event) => onSourceTextChange(event.target.value)}
      />
      <div className="panel-footer">
        <span className="count-label">{sourceText.length} chars</span>
        <button type="button" className="primary-button" onClick={onSubmit} disabled={isSubmitting || !sourceText.trim()}>
          <SendHorizontal size={16} />
          <span>{isSubmitting ? "Translating" : "Translate"}</span>
        </button>
      </div>
    </section>
  );
}
