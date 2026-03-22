import { NextResponse } from "next/server";
import { readdir, readFile } from "fs/promises";
import path from "path";
import { PATHS } from "@/lib/paths";

export async function GET() {
  try {
    const entries = await readdir(PATHS.output, { withFileTypes: true });
    const dateDirs = entries.filter(
      (e) => e.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(e.name)
    );

    const outputs = [];

    for (const dir of dateDirs) {
      const dirPath = path.join(PATHS.output, dir.name);
      const metadataPath = path.join(dirPath, "metadata.json");

      try {
        const raw = await readFile(metadataPath, "utf-8");
        const m = JSON.parse(raw);

        // Normalize to consistent VideoOutput shape regardless of assembler schema
        const slug =
          m.slug ||
          (m.concept || "unknown")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "")
            .slice(0, 60);

        // Handle both file schema variants
        // Variant 1 (original): { files: { "16x9": "file.mp4", "9x16": "file.mp4", thumbnail: "thumb.png" } }
        // Variant 2 (assembler): { outputs: { "16x9": { file: "file.mp4" }, "9x16": { file: "file.mp4" } }, thumbnails: { "16x9": "path" } }
        let files: Record<string, string> = {};
        if (m.files) {
          files = m.files;
        } else if (m.outputs) {
          if (m.outputs["16x9"]?.file) files["16x9"] = m.outputs["16x9"].file;
          if (m.outputs["9x16"]?.file) files["9x16"] = m.outputs["9x16"].file;
          if (m.thumbnails) {
            files.thumbnail = m.thumbnails["16x9"] || m.thumbnails["9x16"] || "";
          }
        }

        // Also scan directory for video files if files map is empty
        if (!files["16x9"] && !files["9x16"]) {
          try {
            const dirFiles = await readdir(dirPath);
            for (const f of dirFiles) {
              if (f.endsWith("-16x9.mp4")) files["16x9"] = f;
              if (f.endsWith("-9x16.mp4")) files["9x16"] = f;
            }
          } catch {
            // skip
          }
        }

        // Scan for thumbnails if not set
        if (!files.thumbnail) {
          try {
            const thumbDir = path.join(dirPath, "thumbnails");
            const thumbFiles = await readdir(thumbDir);
            if (thumbFiles.length > 0) {
              files.thumbnail = `thumbnails/${thumbFiles[0]}`;
            }
          } catch {
            // no thumbnails dir
          }
        }

        // Normalize generation_log
        const generation_log = m.generation_log || {};

        // Build platform_specs from what we know
        const platform_specs = m.platform_specs || {
          tiktok: { aspect: "9:16", file: files["9x16"] || "", max_duration: 180 },
          reels: { aspect: "9:16", file: files["9x16"] || "", max_duration: 90 },
          shorts: { aspect: "9:16", file: files["9x16"] || "", max_duration: 60 },
          youtube: { aspect: "16:9", file: files["16x9"] || "" },
        };

        outputs.push({
          date: dir.name,
          slug,
          concept: m.concept || "Untitled",
          format: m.format || "unknown",
          style: m.style || "unknown",
          duration_seconds: m.duration_seconds || 0,
          files,
          suggested_caption: m.suggested_caption || "",
          suggested_hashtags: m.suggested_hashtags || [],
          platform_specs,
          generation_log,
          assembly_notes: m.assembly_notes || null,
        });
      } catch {
        // Skip dirs without valid metadata
      }
    }

    outputs.sort((a, b) => b.date.localeCompare(a.date));

    return NextResponse.json({ outputs });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read outputs", detail: String(error) },
      { status: 500 }
    );
  }
}
