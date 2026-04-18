import OpenAI from "openai";

export interface VerificationResult {
  verdict: "Real" | "Fake" | "Misleading" | "Unverified";
  aiProbability: number;
  summary: string;
  detailedAnalysis: string[];
  sources: { title: string; url: string }[];
}

const getFirstNonEmpty = (values: Array<string | undefined>): string | undefined => {
  for (const value of values) {
    const trimmed = value?.trim().replace(/^['\"]|['\"]$/g, "");
    if (trimmed) {
      return trimmed;
    }
  }
  return undefined;
};

function getClient() {
  const viteEnv = (import.meta.env ?? {}) as Record<string, string | undefined>;
  const processEnv = typeof process !== "undefined" ? process.env : {};

  const apiKey = getFirstNonEmpty([
    viteEnv.VITE_OPENAI_API_KEY,
    processEnv.OPENAI_API_KEY,
  ]);

  if (!apiKey) {
    return null;
  }

  return new OpenAI({ 
    apiKey, 
    dangerouslyAllowBrowser: true 
  });
}

const SYSTEM_INSTRUCTION = `You are an expert fact-checker. Focus on high factual accuracy.
Return a JSON object with:
{
  "verdict": "Real" | "Fake" | "Misleading" | "Unverified",
  "aiProbability": 0-100,
  "summary": "Brief summary",
  "detailedAnalysis": ["point 1", "point 2"],
  "sources": [{"title": "source title", "url": "url"}]
}`;

export async function verifyWithOpenAI(
  text: string,
  image?: { data: string; mimeType: string }
): Promise<VerificationResult | null> {
  const openai = getClient();
  if (!openai) return null;

  try {
    const messages: any[] = [
      { role: "system", content: SYSTEM_INSTRUCTION },
    ];

    const content: any[] = [];
    if (text.trim()) {
      content.push({ type: "text", text: `Verify this claim: ${text}` });
    }
    if (image) {
      content.push({
        type: "image_url",
        image_url: {
          url: `data:${image.mimeType};base64,${image.data}`,
        },
      });
    }

    messages.push({ role: "user", content });

    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      messages,
      response_format: { type: "json_object" },
    });

    const resultText = response.choices[0].message.content;
    if (!resultText) return null;

    const parsed = JSON.parse(resultText);
    return {
      verdict: parsed.verdict || "Unverified",
      aiProbability: parsed.aiProbability || 0,
      summary: parsed.summary || "No summary provided.",
      detailedAnalysis: parsed.detailedAnalysis || [],
      sources: parsed.sources || [],
    };
  } catch (error) {
    console.error("OpenAI verification failed:", error);
    return null;
  }
}
