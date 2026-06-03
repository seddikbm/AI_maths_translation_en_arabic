import { FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { DirectionToggle } from "./DirectionToggle";
import { ProgressOverlay } from "./ProgressOverlay";

interface DocumentTranslatorProps {
  direction: "en2ar" | "ar2en";
  progress: number;
  isSubmitting: boolean;
  ocrBackend: string;
  onDirectionChange: (direction: "en2ar" | "ar2en") => void;
  onSubmit: (file: File) => void;
}

export function DocumentTranslator({
  direction,
  progress,
  isSubmitting,
  ocrBackend,
  onDirectionChange,
  onSubmit
}: DocumentTranslatorProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function handleFile(file: File | null) {
    if (!file) {
      return;
    }
    setSelectedFile(file);
  }

  return (
    <section className="panel composer-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Document</p>
          <h2>PDF Translation</h2>
        </div>
        <DirectionToggle direction={direction} onChange={onDirectionChange} />
      </div>
      {isSubmitting ? <ProgressOverlay progress={progress} label="Processing PDF" /> : null}
      <button
        type="button"
        className={`dropzone ${isDragging ? "dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          handleFile(event.dataTransfer.files?.[0] ?? null);
        }}
      >
        <FileUp size={28} />
        <span>{selectedFile ? selectedFile.name : "Choose a PDF"}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        hidden
        onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
      />
      <div className="panel-footer">
        <span className="count-label">{ocrBackend ? `OCR: ${ocrBackend}` : "Awaiting upload"}</span>
        <button
          type="button"
          className="primary-button"
          disabled={!selectedFile || isSubmitting}
          onClick={() => selectedFile && onSubmit(selectedFile)}
        >
          <FileUp size={16} />
          <span>{isSubmitting ? "Translating" : "Translate PDF"}</span>
        </button>
      </div>
    </section>
  );
}
