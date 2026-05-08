import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { translateDocument, translateText, type Direction } from "../services/api";

export function useTranslation() {
  const [direction, setDirection] = useState<Direction>("en2ar");
  const [sourceText, setSourceText] = useState("");
  const [translatedText, setTranslatedText] = useState("");
  const [textBackend, setTextBackend] = useState("");
  const [documentBackend, setDocumentBackend] = useState("");
  const [ocrBackend, setOcrBackend] = useState("");
  const [documentUrl, setDocumentUrl] = useState("");
  const [isSubmittingText, setIsSubmittingText] = useState(false);
  const [isSubmittingDocument, setIsSubmittingDocument] = useState(false);
  const [documentProgress, setDocumentProgress] = useState(0);
  const [error, setError] = useState("");

  const deferredSourceText = useDeferredValue(sourceText);
  const previewDirection = direction === "en2ar" ? "English to Arabic" : "Arabic to English";

  useEffect(() => {
    return () => {
      if (documentUrl) {
        URL.revokeObjectURL(documentUrl);
      }
    };
  }, [documentUrl]);

  async function submitText() {
    if (!sourceText.trim()) {
      return;
    }
    setError("");
    setIsSubmittingText(true);
    try {
      const response = await translateText(sourceText.trim(), direction);
      startTransition(() => {
        setTranslatedText(response.translated_text);
        setTextBackend(response.backend);
      });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Text translation failed.");
    } finally {
      setIsSubmittingText(false);
    }
  }

  async function submitDocument(file: File) {
    setError("");
    setDocumentProgress(8);
    setIsSubmittingDocument(true);
    try {
      const response = await translateDocument(file, direction, setDocumentProgress);
      const url = URL.createObjectURL(response.blob);
      startTransition(() => {
        if (documentUrl) {
          URL.revokeObjectURL(documentUrl);
        }
        setDocumentUrl(url);
        setDocumentBackend(response.backend);
        setOcrBackend(response.ocrBackend);
        setDocumentProgress(100);
      });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Document translation failed.");
    } finally {
      setIsSubmittingDocument(false);
    }
  }

  return {
    direction,
    setDirection,
    sourceText,
    setSourceText,
    translatedText,
    textBackend,
    documentBackend,
    ocrBackend,
    documentUrl,
    isSubmittingText,
    isSubmittingDocument,
    documentProgress,
    error,
    deferredSourceText,
    previewDirection,
    submitText,
    submitDocument
  };
}
