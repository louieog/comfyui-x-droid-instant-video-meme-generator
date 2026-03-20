export interface VideoOutput {
  date: string;
  slug: string;
  concept: string;
  format: string;
  style: string;
  duration_seconds: number;
  files: { "16x9"?: string; "9x16"?: string; thumbnail?: string };
  suggested_caption: string;
  suggested_hashtags: string[];
  platform_specs: Record<
    string,
    { aspect: string; file: string; max_duration?: number }
  >;
  generation_log: {
    images: { model: string; count: number; status: string };
    tts: { model: string; voice: string; lines: number; status: string };
    video: { model: string; clips: number; status: string };
    lip_sync: {
      model: string;
      clips: number;
      status: string;
      note?: string;
    };
  };
}

export interface ContentRequest {
  id: string;
  created_at: string;
  concept: string;
  format: string;
  style: string;
  duration_target: number;
  model_overrides?: {
    image?: string;
    video?: string;
    tts?: string;
    lip_sync?: string;
  };
  reference_image?: string;
  status:
    | "pending"
    | "brief_ready"
    | "generating"
    | "review"
    | "complete"
    | "failed";
}

export interface ProductionBrief {
  concept: string;
  format: string;
  trend_score?: number;
  style: string;
  duration_target_seconds: number;
  scenes: Scene[];
  characters: Character[];
  generation_requirements: {
    character_consistency: boolean;
    lip_sync_needed: boolean;
    models_preferred: Record<string, string>;
  };
}

export interface Scene {
  scene_id: number;
  beat: string;
  duration_seconds: number;
  visual: string;
  camera: string;
  characters_present: string[];
  dialogue: {
    character: string;
    line: string;
    voice_style: string;
    emotion: string;
  }[];
  sfx: string[];
  music_cue: string;
  text_overlay: string | null;
}

export interface Character {
  id: string;
  description: string;
}

export interface ModelCategory {
  image: string[];
  video: string[];
  audio: string[];
  lip_sync: string[];
}

export interface SeedList {
  updated: string;
  topics: { theme: string; notes: string; styles: string[] }[];
  avoid: string[];
}
