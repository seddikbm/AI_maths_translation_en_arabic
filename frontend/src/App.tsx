import { useEffect, useState } from "react";
import { DocumentTranslator } from "./components/DocumentTranslator";
import { Header } from "./components/Header";
import { ResultViewer } from "./components/ResultViewer";
import { TextTranslator } from "./components/TextTranslator";
import { useTranslation } from "./hooks/useTranslation";

type Mode = "text" | "document";

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mode, setMode] = useState<Mode>("text");
  const translation = useTranslation();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function downloadResult() {
    if (!translation.documentUrl) {
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = translation.documentUrl;
    anchor.download = `mathtrans_${translation.direction}.pdf`;
    anchor.click();
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <main className="workspace">
        <Header theme={theme} onThemeToggle={() => setTheme(theme === "light" ? "dark" : "light")} />
        <div className="mode-switch" role="tablist" aria-label="Workspace mode">
          <button
            type="button"
            className={mode === "text" ? "active" : ""}
            onClick={() => setMode("text")}
          >
            Text
          </button>
          <button
            type="button"
            className={mode === "document" ? "active" : ""}
            onClick={() => setMode("document")}
          >
            Document
          </button>
        </div>

        {translation.error ? <div className="error-banner">{translation.error}</div> : null}

        <section className="content-grid">
          {mode === "text" ? (
            <>
              <TextTranslator
                direction={translation.direction}
                sourceText={translation.sourceText}
                previewDirection={translation.previewDirection}
                onDirectionChange={translation.setDirection}
                onSourceTextChange={translation.setSourceText}
                onSubmit={translation.submitText}
                isSubmitting={translation.isSubmittingText}
              />
              <ResultViewer
                title="Translated Text"
                subtitle={translation.previewDirection}
                content={translation.translatedText}
                contentDirection={translation.direction === "en2ar" ? "rtl" : "ltr"}
                backend={translation.textBackend}
              />
            </>
          ) : (
            <>
              <DocumentTranslator
                direction={translation.direction}
                progress={translation.documentProgress}
                isSubmitting={translation.isSubmittingDocument}
                ocrBackend={translation.ocrBackend}
                onDirectionChange={translation.setDirection}
                onSubmit={translation.submitDocument}
              />
              <ResultViewer
                title="Translated PDF"
                subtitle="Preview"
                content=""
                backend={translation.documentBackend}
                documentUrl={translation.documentUrl}
                onDownload={downloadResult}
              />
            </>
          )}
        </section>
      </main>
    </div>
  );
}
