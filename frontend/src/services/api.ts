export type Direction = "en2ar" | "ar2en";

export interface TranslateTextResponse {
  direction: Direction;
  source_text: string;
  translated_text: string;
  backend: string;
}

export interface TranslateDocumentResponse {
  blob: Blob;
  backend: string;
  ocrBackend: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

<<<<<<< HEAD
=======
async function readErrorMessage(response: Blob | string | null, status: number): Promise<string> {
  const fallback = `Request failed with status ${status}`;
  const text = response instanceof Blob ? await response.text() : response;
  if (!text) {
    return fallback;
  }

  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail) {
      return JSON.stringify(payload.detail);
    }
  } catch {
    return text;
  }

  return text;
}

>>>>>>> codex/mathtrans-current-version
export async function translateText(text: string, direction: Direction): Promise<TranslateTextResponse> {
  const response = await fetch(`${API_BASE_URL}/api/translate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ text, direction })
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as TranslateTextResponse;
}

export function translateDocument(
  file: File,
  direction: Direction,
  onProgress?: (progress: number) => void
): Promise<TranslateDocumentResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("direction", direction);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api/translate/document`);
    xhr.responseType = "blob";

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || !onProgress) {
        return;
      }
      onProgress(Math.round((event.loaded / event.total) * 40));
    };

    xhr.onprogress = (event) => {
      if (!event.lengthComputable || !onProgress) {
        return;
      }
      onProgress(40 + Math.round((event.loaded / event.total) * 60));
    };

<<<<<<< HEAD
    xhr.onload = () => {
=======
    xhr.onload = async () => {
>>>>>>> codex/mathtrans-current-version
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({
          blob: xhr.response,
          backend: xhr.getResponseHeader("X-Translation-Backend") ?? "unknown",
          ocrBackend: xhr.getResponseHeader("X-OCR-Backend") ?? "unknown"
        });
        return;
      }
<<<<<<< HEAD
      reject(new Error(xhr.responseText || `Request failed with status ${xhr.status}`));
=======
      reject(new Error(await readErrorMessage(xhr.response, xhr.status)));
>>>>>>> codex/mathtrans-current-version
    };

    xhr.onerror = () => reject(new Error("Network error while uploading the PDF."));
    xhr.send(form);
  });
}
