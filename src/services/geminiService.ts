/**
 * geminiService.ts — Flask-backed version.
 *
 * All AI logic has been moved to the Flask backend (backend/verify.py).
 * This module now calls the local /api/verify endpoint and returns the
 * same VerificationResult shape as before — zero changes to the UI.
 */

export interface VerificationResult {
  verdict: "Real" | "Fake" | "Misleading" | "Unverified";
  aiProbability: number;
  summary: string;
  detailedAnalysis: string[];
  sources: { title: string; url: string }[];
}

export async function verifyContent(
  text: string,
  image?: { data: string; mimeType: string }
): Promise<VerificationResult> {
  const body: Record<string, unknown> = { text };
  if (image) {
    body.image = image;
  }

  let response: Response;
  try {
    response = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (networkError) {
    throw new Error(
      "Network error: Could not reach the TruthLens server. " +
        "Make sure Flask is running (`python app.py`) and try again."
    );
  }

  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new Error("Server returned an unexpected response. Please try again.");
  }

  if (!response.ok) {
    const errorMsg =
      (json as { error?: string })?.error ||
      `Server error ${response.status}: ${response.statusText}`;
    throw new Error(errorMsg);
  }

  return json as VerificationResult;
}