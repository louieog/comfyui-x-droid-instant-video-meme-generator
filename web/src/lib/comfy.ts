import { readFile } from "fs/promises";
import { PATHS } from "./paths";

const COMFY_CLOUD_BASE = "https://cloud.comfy.org";

export async function getApiKey(): Promise<string> {
  const envContent = await readFile(PATHS.env, "utf-8");
  const match = envContent.match(/^COMFY_CLOUD_API_KEY=(.+)$/m);
  if (!match) {
    throw new Error("COMFY_CLOUD_API_KEY not found in .env");
  }
  return match[1].trim();
}

interface ModelOption {
  name: string;
  value: string;
}

interface ModelCategory {
  image: ModelOption[];
  video: ModelOption[];
  audio: ModelOption[];
  lipsync: ModelOption[];
}

export async function getAvailableModels(): Promise<ModelCategory> {
  const apiKey = await getApiKey();

  const res = await fetch(`${COMFY_CLOUD_BASE}/api/object_info`, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
  });

  if (!res.ok) {
    throw new Error(`ComfyUI Cloud API error: ${res.status} ${res.statusText}`);
  }

  const data = await res.json();

  const categories: ModelCategory = {
    image: [],
    video: [],
    audio: [],
    lipsync: [],
  };

  // Categorize partner nodes by type based on common naming patterns
  for (const [nodeName, nodeInfo] of Object.entries(data)) {
    const info = nodeInfo as Record<string, unknown>;
    const name = nodeName.toLowerCase();
    const entry: ModelOption = {
      name: nodeName,
      value: nodeName,
    };

    if (
      name.includes("flux") ||
      name.includes("imagen") ||
      name.includes("stable") ||
      name.includes("dall")
    ) {
      categories.image.push(entry);
    } else if (
      name.includes("kling") ||
      name.includes("wan") ||
      name.includes("hunyuan") ||
      name.includes("ltx") ||
      name.includes("video")
    ) {
      // Check for lip sync specifically
      if (name.includes("lipsync") || name.includes("lip_sync")) {
        categories.lipsync.push(entry);
      } else {
        categories.video.push(entry);
      }
    } else if (
      name.includes("tts") ||
      name.includes("elevenlabs") ||
      name.includes("audio") ||
      name.includes("speech")
    ) {
      categories.audio.push(entry);
    } else if (name.includes("lipsync") || name.includes("lip_sync")) {
      categories.lipsync.push(entry);
    }
  }

  return categories;
}
