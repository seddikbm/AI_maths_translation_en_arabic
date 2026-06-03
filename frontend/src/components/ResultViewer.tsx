import { Download, FileText } from "lucide-react";

interface ResultViewerProps {
  title: string;
  subtitle: string;
  content: string;
  contentDirection?: "ltr" | "rtl";
  backend?: string;
  documentUrl?: string;
  onDownload?: () => void;
}

export function ResultViewer({
  title,
  subtitle,
  content,
  contentDirection = "ltr",
  backend,
  documentUrl,
  onDownload
}: ResultViewerProps) {
  return (
    <section className="panel result-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">{subtitle}</p>
          <h2>{title}</h2>
        </div>
        {backend ? <span className="status-pill">{backend}</span> : null}
      </div>
      {documentUrl ? (
        <div className="document-preview">
          <div className="document-preview-toolbar">
            <span className="status-pill">
              <FileText size={14} />
              PDF
            </span>
            <button type="button" className="secondary-button" onClick={onDownload}>
              <Download size={16} />
              <span>Download</span>
            </button>
          </div>
          <iframe title="Translated PDF preview" src={documentUrl} />
        </div>
      ) : (
        <div className="result-copy" dir={contentDirection}>
          <pre lang={contentDirection === "rtl" ? "ar" : "en"}>{content || "Result will appear here."}</pre>
        </div>
      )}
    </section>
  );
}
