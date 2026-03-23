"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { ChevronDown, ChevronUp, Upload, Sparkles } from "lucide-react";

const FORMAT_OPTIONS = [
  { value: "auto", label: "Auto (recommended)" },
  { value: "mini-drama", label: "Mini Drama" },
  { value: "text-meme", label: "Text Meme" },
  { value: "reaction", label: "Reaction" },
  { value: "skit", label: "Skit" },
  { value: "custom", label: "Custom" },
];

const STYLE_OPTIONS = [
  { value: "absurdist", label: "Absurdist" },
  { value: "wholesome", label: "Wholesome" },
  { value: "dark-humor", label: "Dark Humor" },
  { value: "relatable", label: "Relatable" },
  { value: "cinematic", label: "Cinematic" },
];

const IMAGE_MODELS = [
  { value: "FluxKontextProImageNode", label: "Flux Kontext Pro" },
  { value: "Flux2ProImageNode", label: "Flux 2 Pro" },
  { value: "Flux2MaxImageNode", label: "Flux 2 Max" },
  { value: "FluxProUltraImageNode", label: "Flux Pro Ultra" },
  { value: "IdeogramV3", label: "Ideogram v3" },
  { value: "RecraftV4TextToImageNode", label: "Recraft v4" },
  { value: "OpenAIDalle3", label: "DALL-E 3" },
  { value: "OpenAIGPTImage1", label: "GPT Image 1" },
  { value: "StabilityStableImageUltraNode", label: "Stability Ultra" },
  { value: "KlingImageGenerationNode", label: "Kling Image" },
  { value: "NanoBananaProImageNode", label: "Nano Banana Pro" },
  { value: "GeminiFlash25ImageNode", label: "Gemini Flash 2.5" },
  { value: "LumaImageNode", label: "Luma Image" },
  { value: "RunwayTextToImageNode", label: "Runway" },
];

const VIDEO_MODELS = [
  { value: "kling-v2-master", label: "Kling v2 Master", hasAudio: false },
  { value: "kling-v2-1-master", label: "Kling v2.1 Master", hasAudio: false },
  { value: "kling-v2-5-turbo", label: "Kling v2.5 Turbo", hasAudio: false },
  { value: "kling-v3", label: "Kling 3", hasAudio: false },
  { value: "KlingTextToVideoWithAudio", label: "Kling v2 + Audio", hasAudio: true },
  { value: "KlingImageToVideoWithAudio", label: "Kling I2V + Audio", hasAudio: true },
  { value: "RunwayImageToVideoNodeGen4", label: "Runway Gen4", hasAudio: false },
  { value: "LumaImageToVideoNode", label: "Luma", hasAudio: false },
  { value: "Veo3VideoGenerationNode", label: "Veo 3 (native audio)", hasAudio: true },
  { value: "VeoVideoGenerationNode", label: "Veo 2", hasAudio: false },
  { value: "MinimaxHailuoVideoNode", label: "Minimax / Hailuo", hasAudio: false },
  { value: "Vidu3ImageToVideoNode", label: "Vidu 3", hasAudio: false },
  { value: "WanImageToVideoApi", label: "Wan", hasAudio: false },
  { value: "WanSoundImageToVideo", label: "Wan + Sound", hasAudio: true },
  { value: "HunyuanImageToVideo", label: "Hunyuan", hasAudio: false },
  { value: "OpenAIVideoSora2", label: "Sora 2", hasAudio: false },
];

const VOICE_OPTIONS = [
  { value: "none", label: "None (video model handles audio)" },
  { value: "George (male, british)", label: "George (male, british)" },
  { value: "Roger (male, american)", label: "Roger (male, american)" },
  { value: "Sarah (female, american)", label: "Sarah (female, american)" },
  { value: "Laura (female, american)", label: "Laura (female, american)" },
  { value: "Charlie (male, australian)", label: "Charlie (male, australian)" },
  { value: "Callum (male, american)", label: "Callum (male, american)" },
  { value: "River (neutral, american)", label: "River (neutral, american)" },
  { value: "Harry (male, american)", label: "Harry (male, american)" },
  { value: "Liam (male, american)", label: "Liam (male, american)" },
  { value: "Alice (female, british)", label: "Alice (female, british)" },
  { value: "Matilda (female, american)", label: "Matilda (female, american)" },
  { value: "Will (male, american)", label: "Will (male, american)" },
  { value: "Jessica (female, american)", label: "Jessica (female, american)" },
  { value: "Eric (male, american)", label: "Eric (male, american)" },
  { value: "Bella (female, american)", label: "Bella (female, american)" },
  { value: "Chris (male, american)", label: "Chris (male, american)" },
  { value: "Brian (male, american)", label: "Brian (male, american)" },
  { value: "Daniel (male, british)", label: "Daniel (male, british)" },
  { value: "Lily (female, british)", label: "Lily (female, british)" },
  { value: "Adam (male, american)", label: "Adam (male, american)" },
  { value: "Bill (male, american)", label: "Bill (male, american)" },
];

const LIPSYNC_OPTIONS = [
  { value: "KlingLipSyncAudioToVideoNode", label: "Kling Lip Sync (Audio)" },
  { value: "KlingLipSyncTextToVideoNode", label: "Kling Lip Sync (Text)" },
  { value: "none", label: "None" },
];

export default function CreatePage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [concept, setConcept] = useState("");
  const [format, setFormat] = useState("auto");
  const [style, setStyle] = useState("dark-humor");
  const [duration, setDuration] = useState(15);
  const [imageModel, setImageModel] = useState("FluxKontextProImageNode");
  const [videoModel, setVideoModel] = useState("kling-v2-master");
  const [voice, setVoice] = useState("George (male, british)");
  const [lipSync, setLipSync] = useState("KlingLipSyncAudioToVideoNode");
  const [refImage, setRefImage] = useState<File | null>(null);

  const selectedVideoModel = VIDEO_MODELS.find((m) => m.value === videoModel);
  const videoHasAudio = selectedVideoModel?.hasAudio ?? false;

  function handleVideoModelChange(val: string) {
    setVideoModel(val);
    const model = VIDEO_MODELS.find((m) => m.value === val);
    if (model?.hasAudio) {
      setVoice("none");
      setLipSync("none");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!concept.trim()) return;
    setSubmitting(true);

    try {
      const body: Record<string, unknown> = {
        concept: concept.trim(),
        format,
        style,
        duration_target: duration,
        model_overrides: { image: imageModel, video: videoModel, tts: voice, lip_sync: lipSync },
      };
      const res = await fetch("/api/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.id) {
        router.push(`/create/${data.id}/brief`);
      }
    } catch {
      // handle error
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <Header title="Create Video" description="Describe your content and choose your models" />

      <form onSubmit={handleSubmit} className="max-w-3xl">
        <Card>
          <CardContent className="p-6 space-y-6">
            <div>
              <label className="block text-sm font-medium mb-2">Concept</label>
              <Textarea
                value={concept}
                onChange={(e) => setConcept(e.target.value)}
                placeholder="Describe your video idea... e.g., A cat news anchor delivering satirical commentary on current events"
                rows={3}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Format</label>
                <Select options={FORMAT_OPTIONS} value={format} onChange={setFormat} />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Style</label>
                <Select options={STYLE_OPTIONS} value={style} onChange={setStyle} />
              </div>
            </div>

            <Slider
              label="Duration"
              min={5}
              max={90}
              step={5}
              value={duration}
              onChange={setDuration}
            />

            <div>
              <label className="block text-sm font-medium mb-2">Reference Image (optional)</label>
              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => setRefImage(e.target.files?.[0] || null)}
                />
                {refImage ? (
                  <p className="text-sm">{refImage.name}</p>
                ) : (
                  <>
                    <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">Click or drag to upload a reference image</p>
                  </>
                )}
              </div>
            </div>

            <div className="border border-border rounded-lg">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center justify-between w-full p-4 text-sm font-medium hover:bg-secondary/50 transition-colors rounded-lg"
              >
                <span>Advanced: Model Selection</span>
                {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>

              {showAdvanced && (
                <div className="p-4 pt-0 space-y-4 border-t border-border">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">Image Model</label>
                      <Select options={IMAGE_MODELS} value={imageModel} onChange={setImageModel} />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">Video Model</label>
                      <Select options={VIDEO_MODELS} value={videoModel} onChange={handleVideoModelChange} />
                    </div>
                  </div>

                  {videoHasAudio && (
                    <div className="bg-primary/10 border border-primary/20 rounded-lg px-3 py-2">
                      <p className="text-xs text-primary">
                        {selectedVideoModel?.label} generates audio natively -- TTS and lip sync stages will be skipped.
                        You can still override below if you want separate audio generation.
                      </p>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-4">
                    <div className={videoHasAudio ? "opacity-50" : ""}>
                      <label className="block text-sm font-medium mb-2">
                        Voice (TTS)
                        {videoHasAudio && <span className="text-xs text-muted-foreground ml-2">-- skipped</span>}
                      </label>
                      <Select options={VOICE_OPTIONS} value={voice} onChange={setVoice} />
                    </div>
                    <div className={videoHasAudio ? "opacity-50" : ""}>
                      <label className="block text-sm font-medium mb-2">
                        Lip Sync
                        {videoHasAudio && <span className="text-xs text-muted-foreground ml-2">-- skipped</span>}
                      </label>
                      <Select options={LIPSYNC_OPTIONS} value={lipSync} onChange={setLipSync} />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <Button type="submit" size="lg" className="w-full" disabled={!concept.trim() || submitting}>
              <Sparkles className="w-4 h-4 mr-2" />
              {submitting ? "Submitting..." : "Generate Video"}
            </Button>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
